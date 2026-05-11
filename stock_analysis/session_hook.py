"""Claude Code hooks — SessionStart 开始会话, Stop 关闭会话"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from session_tracker import init_session_tracker, start_session, get_active_session, end_session

init_session_tracker()
action = sys.argv[1] if len(sys.argv) > 1 else "stop"

if action == "start":
    sid = start_session()
    print(f"Session {sid} started")

elif action == "stop":
    session = get_active_session()
    if session:
        end_session(session["session_id"])
        errs = session.get("error_count", 0)
        print(f"Session {session['session_id']} closed ({errs} errors)")
    else:
        print("No active session")
