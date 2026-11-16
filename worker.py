import asyncio
import random
import sys
from datetime import datetime, timedelta
from sqlalchemy.orm.attributes import flag_modified
from app.database import SessionLocal
from app.models import DiscordAccount, Schedule, MessageLog
from app.crypto import decrypt_token
from app.discord_api import send_channel_message, delete_channel_message, DiscordRateLimitError

active_workers = {}

def _format_duration(seconds: int) -> str:
    jam = seconds // 3600
    menit = (seconds % 3600) // 60
    detik = seconds % 60
    return f"{jam}j {menit}m {detik}d" if jam > 0 else f"{menit}m {detik}d"

def _sync_next_run(sched: Schedule):
    upcoming = []
    for target in (sched.target_channels or []):
        if target.get("status") == "Running" and target.get("next_run_at"):
            try:
                upcoming.append(datetime.fromisoformat(target["next_run_at"]))
            except ValueError:
                pass
    sched.next_run_at = min(upcoming) if upcoming else None

async def account_worker(account_id: int):
    last_message_ids = {}
    try:
        while True:
            due_channels = []
            token = None

            with SessionLocal() as db:
                sched = db.query(Schedule).filter(Schedule.account_id == account_id).first()
                acct = db.query(DiscordAccount).filter(DiscordAccount.id == account_id).first()

                if not acct or not sched:
                    print(f"[Worker] Account {account_id} deleted. Stopping task.")
                    break

                channels = sched.target_channels or []
                active_channels = [c for c in channels if c.get("status") == "Running"]

                # Jika tidak ada satupun channel yang Running, hentikan task akun ini
                if not active_channels:
                    sched.status = "Paused"
                    sched.next_run_at = None
                    db.commit()
                    print(f"[Worker] Account {account_id} has no running channels. Stopping task.")
                    break

                token = decrypt_token(acct.encrypted_token)
                now = datetime.now()

                for idx, ch in enumerate(channels):
                    if ch.get("status") != "Running":
                        continue

                    next_iso = ch.get("next_run_at")
                    is_due = True
                    if next_iso:
                        try:
                            if now < datetime.fromisoformat(next_iso):
                                is_due = False
                        except ValueError:
                            is_due = True

                    if is_due:
                        due_channels.append((idx, dict(ch), sched.message_content, sched.min_delay, sched.max_delay, sched.auto_delete))

            if not due_channels:
                await asyncio.sleep(2)
                continue

            for idx, ch, fallback_msg, fallback_min, fallback_max, fallback_del in due_channels:
                ch_id = ch["id"]
                ch_name = ch.get("name", ch_id)
                guild_name = ch.get("guild_name", "Server")
                label = f"#{ch_name} ({guild_name})"

                msg_content = (ch.get("message_content") or fallback_msg or "").strip()
                auto_delete = ch.get("auto_delete") if ch.get("auto_delete") is not None else fallback_del
                min_delay = max(15, int(ch.get("min_delay") or fallback_min or 1800))
                max_delay = max(min_delay + 5, int(ch.get("max_delay") or fallback_max or 1830))

                if not msg_content:
                    with SessionLocal() as db:
                        sched_u = db.query(Schedule).filter(Schedule.account_id == account_id).first()
                        if sched_u and sched_u.target_channels:
                            for target in sched_u.target_channels:
                                if target["id"] == ch_id:
                                    target["status"] = "Paused"
                                    target.pop("next_run_at", None)
                            _sync_next_run(sched_u)
                            flag_modified(sched_u, "target_channels")
                            db.commit()
                    continue

                # 1. Hapus pesan lama jika auto_delete aktif
                if auto_delete and ch_id in last_message_ids:
                    try:
                        await delete_channel_message(token, ch_id, last_message_ids[ch_id])
                        with SessionLocal() as db:
                            db.add(MessageLog(
                                account_id=account_id,
                                log_type="DELETED",
                                channel_label=label,
                                detail="Pesan sebelumnya dihapus."
                            ))
                            db.commit()
                    except Exception:
                        pass
                    await asyncio.sleep(1.5)

                # 2. Kirim pesan baru
                try:
                    msg_id = await send_channel_message(token, ch_id, msg_content)
                    last_message_ids[ch_id] = msg_id
                    sent_now = datetime.now()
                    delay = random.randint(min_delay, max_delay)
                    next_time = sent_now + timedelta(seconds=delay)

                    with SessionLocal() as db:
                        sched_u = db.query(Schedule).filter(Schedule.account_id == account_id).first()
                        if sched_u and sched_u.target_channels:
                            for target in sched_u.target_channels:
                                if target["id"] == ch_id:
                                    target["last_sent_at"] = sent_now.isoformat()
                                    target["next_run_at"] = next_time.isoformat()

                            sched_u.last_sent_at = sent_now
                            _sync_next_run(sched_u)
                            flag_modified(sched_u, "target_channels")

                        db.add(MessageLog(
                            account_id=account_id,
                            log_type="SENT",
                            channel_label=label,
                            detail=f"Terkirim: \"{msg_content[:45]}{'...' if len(msg_content) > 45 else ''}\""
                        ))
                        db.add(MessageLog(
                            account_id=account_id,
                            log_type="SLEEP",
                            channel_label=label,
                            detail=f"CD {_format_duration(delay)} (kirim lagi pukul {next_time.strftime('%H:%M:%S')})."
                        ))
                        db.commit()

                    print(f"[Account {account_id}] [+] Sent to {label} | Next CD: {_format_duration(delay)}")

                except DiscordRateLimitError as rl:
                    retry_time = datetime.now() + timedelta(seconds=rl.retry_after)
                    with SessionLocal() as db:
                        sched_u = db.query(Schedule).filter(Schedule.account_id == account_id).first()
                        if sched_u and sched_u.target_channels:
                            for target in sched_u.target_channels:
                                if target["id"] == ch_id:
                                    target["next_run_at"] = retry_time.isoformat()
                            _sync_next_run(sched_u)
                            flag_modified(sched_u, "target_channels")
                        db.add(MessageLog(
                            account_id=account_id,
                            log_type="SLEEP",
                            channel_label=label,
                            detail=f"Slowmode Discord aktif: tunggu {_format_duration(rl.retry_after)} (kirim pukul {retry_time.strftime('%H:%M:%S')})."
                        ))
                        db.commit()

                    print(f"[Account {account_id}] [429] Slowmode on {label} | Waiting {_format_duration(rl.retry_after)}")

                except Exception as e:
                    retry_time = datetime.now() + timedelta(seconds=60)
                    with SessionLocal() as db:
                        sched_u = db.query(Schedule).filter(Schedule.account_id == account_id).first()
                        if sched_u and sched_u.target_channels:
                            for target in sched_u.target_channels:
                                if target["id"] == ch_id:
                                    target["next_run_at"] = retry_time.isoformat()
                            _sync_next_run(sched_u)
                            flag_modified(sched_u, "target_channels")
                        db.add(MessageLog(
                            account_id=account_id,
                            log_type="ERROR",
                            channel_label=label,
                            detail=str(e)
                        ))
                        db.commit()

                await asyncio.sleep(2)

            await asyncio.sleep(2)

    except asyncio.CancelledError:
        print(f"[Worker] Task for Account {account_id} cancelled.")
    finally:
        if account_id in active_workers:
            del active_workers[account_id]

async def manager_loop():
    print("=======================================")
    print(" PulseCord Multi-Account Worker Engine ")
    print("=======================================")

    while True:
        try:
            with SessionLocal() as db:
                schedules = db.query(Schedule).all()
                for sched in schedules:
                    acc_id = sched.account_id
                    has_running_ch = any(c.get("status") == "Running" for c in (sched.target_channels or []))
                    if (sched.status == "Running" or has_running_ch) and acc_id not in active_workers:
                        print(f"[*] Starting background worker for Account ID: {acc_id}")
                        task = asyncio.create_task(account_worker(acc_id))
                        active_workers[acc_id] = task
                    elif not has_running_ch and sched.status != "Running" and acc_id in active_workers:
                        print(f"[*] Stopping background worker for Account ID: {acc_id}")
                        active_workers[acc_id].cancel()
        except Exception as e:
            print(f"[Manager Error] {str(e)}")

        await asyncio.sleep(3)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(manager_loop())
    except KeyboardInterrupt:
        print("\nWorker Engine Stopped.")