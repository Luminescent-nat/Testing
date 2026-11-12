import sys
sys.path.insert(0, r"D:\MCTEST\test-platform\test-tools")
from common.adb_runner import AdbRunner, normalise_tokens

forms = [
    "settings put global airplane_mode_on 1",
    "settings put system screen_off_timeout 60000",
    'install -r "C:\\tools\\my app.apk"',
    "sm list-volumes public",
]
print("--- normalise_tokens on real f-string / quoted / pipe forms ---")
for f in forms:
    try:
        print(repr(f), "->", normalise_tokens(f))
    except Exception as e:
        print(repr(f), "-> ERROR", e)

print("--- shell() remote single-arg semantics (argv only, no execution) ---")

def make_runner():
    r = AdbRunner.__new__(AdbRunner)
    r.serial = "SER"
    r._adb_prefix = ["adb"]
    r.default_timeout = None
    r.last_command = None
    r.last_error = None
    return r

r = make_runner()
cap = {}
def fake_run(cmd, timeout=None, check=False):
    cap["argv"] = r._full_argv(normalise_tokens(cmd))
    return None
r.run = fake_run
r.shell("ls /sys/block/ | grep mmcblk")
print("shell pipe argv =", cap["argv"])

r2 = make_runner()
cap2 = {}
def fake_run2(cmd, timeout=None, check=False):
    cap2["argv"] = r2._full_argv(normalise_tokens(cmd))
    return None
r2.run = fake_run2
r2.shell("echo ok; echo hacked > marker && echo $(id)")
print("shell metachar argv =", cap2["argv"])

r3 = make_runner()
cap3 = {}
def fake_run3(cmd, timeout=None, check=False):
    cap3["argv"] = r3._full_argv(normalise_tokens(cmd))
    return None
r3.run = fake_run3
joined = " ".join(["fio", "--name=seqread", "--size=64m"])
r3.shell(joined)
print("shell ' '.join(cmd_parts) argv =", cap3["argv"])
