"""Keep the Win32 standard-input handle valid for the whole pytest run.

pytest's default `--capture=fd` redirects file descriptor 0 to the null
device, and on Windows `os.dup2` onto fd 0 CLOSES the handle that was behind
it. `subprocess.Popen(stdin=None)` does not read fd 0: it asks Win32 for
`GetStdHandle(STD_INPUT_HANDLE)`, which is now that closed handle, and dies in
`_make_inheritable` with `OSError: [WinError 6] The handle is invalid`. Every
test (or collection-time probe) that starts a child without an explicit
`stdin=` then fails. It shows up wherever stdin is not a console - the Stop
hook's verify gate, a `<NUL` redirect, a CI pipe.

The fix is at the source: point STD_INPUT_HANDLE at a handle of our own, one
that no CRT file descriptor owns, so capture cannot close it. Children then
inherit the null device, which is also what a hook child should read: EOF.

`install()` is a no-op off Windows and idempotent.
"""
import sys

_STD_INPUT_HANDLE = -10
_installed = False


def install():
    """Replace the process's Win32 stdin handle with an owned NUL handle."""
    global _installed  # pylint: disable=global-statement
    if _installed or sys.platform != "win32":
        return
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.HANDLE]
    kernel32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    generic_read, share_rw, open_existing, inheritable = 0x80000000, 0x3, 3, 1

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", wintypes.LPVOID),
                    ("bInheritHandle", wintypes.BOOL)]

    sa = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), None, inheritable)
    handle = kernel32.CreateFileW("NUL", generic_read, share_rw, ctypes.byref(sa),
                                  open_existing, 0, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        return  # leave the handle as it was; a failure here must not fail the run
    if kernel32.SetStdHandle(_STD_INPUT_HANDLE & 0xFFFFFFFF, handle):
        _installed = True
