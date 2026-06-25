"""
Windows 自動起動の登録・解除を管理するモジュール。

レジストリキー HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run を使用。
管理者権限不要、現在ユーザーのみに適用。

開発版（非凍結）では VBS ランチャー経由で起動する:
  ~/.claude_hourglass/launch_hourglass.vbs
    └─ pythonw.exe -m claude_hourglass.main (作業ディレクトリ=プロジェクトルート)

PyInstaller 等で EXE 化した場合は VBS を経由せず EXE パスを直接登録する。
"""

from __future__ import annotations
import sys
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"
_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "ClaudeHourglass"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def launcher_path() -> Path:
    """VBS ランチャーのパス: ~/.claude_hourglass/launch_hourglass.vbs"""
    return Path.home() / ".claude_hourglass" / "launch_hourglass.vbs"


def _project_root() -> Path:
    """プロジェクトルート (このファイルは claude_hourglass/ 下にある)"""
    return Path(__file__).resolve().parent.parent


def _pythonw_exe() -> str:
    """
    コンソールなし起動用の pythonw.exe パスを返す。
    pythonw.exe が見つからない場合は python.exe にフォールバック。
    """
    py = Path(sys.executable)
    candidate = py.parent / "pythonw.exe"
    return str(candidate) if candidate.exists() else str(py)


# ---------------------------------------------------------------------------
# VBS launcher generation
# ---------------------------------------------------------------------------

def write_launcher_script() -> Path:
    """
    VBS ランチャーを ~/.claude_hourglass/launch_hourglass.vbs に生成して返す。

    VBS の役割:
    - 作業ディレクトリをプロジェクトルートに設定
    - pythonw.exe でコンソールなし起動
    - Chr(34) でパス中のスペースを正しくクォート
    """
    path = launcher_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    pythonw = _pythonw_exe()
    project_root = str(_project_root())

    # Chr(34) = '"' — VBS のエスケープより読みやすくクォート問題を回避する
    vbs = "\r\n".join([
        'Set oShell = CreateObject("WScript.Shell")',
        f'oShell.CurrentDirectory = "{project_root}"',
        (
            f'oShell.Run Chr(34) & "{pythonw}" & Chr(34)'
            f' & " -m claude_hourglass.main", 0, False'
        ),
        "",  # 末尾改行
    ])
    path.write_text(vbs, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_startup_command() -> str:
    """
    レジストリ Run キーに登録するコマンド文字列を返す。
    - 凍結 EXE の場合: EXE パス直接
    - 通常 Python の場合: wscript.exe "<vbs_path>"
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'wscript.exe "{launcher_path()}"'


def is_startup_enabled() -> bool:
    """レジストリ Run キーに登録されているかを返す。"""
    if not _IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable_startup() -> None:
    """
    VBS ランチャーを生成し、レジストリ Run キーに登録する。
    失敗時は OSError を送出する。
    """
    if not _IS_WINDOWS:
        raise OSError("自動起動は Windows のみ対応しています")

    import winreg

    if not getattr(sys, "frozen", False):
        write_launcher_script()

    cmd = get_startup_command()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
    except OSError as e:
        raise OSError(f"レジストリを開けません: {e}") from e
    try:
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
    except OSError as e:
        raise OSError(f"レジストリへの書き込みに失敗しました: {e}") from e
    finally:
        winreg.CloseKey(key)


def disable_startup() -> None:
    """
    レジストリ Run キーから登録を解除する。
    未登録の場合は何もしない。失敗時は OSError を送出する。
    """
    if not _IS_WINDOWS:
        return

    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
    except OSError as e:
        raise OSError(f"レジストリを開けません: {e}") from e
    try:
        winreg.DeleteValue(key, _APP_NAME)
    except FileNotFoundError:
        pass  # 未登録 → 正常
    except OSError as e:
        raise OSError(f"レジストリからの削除に失敗しました: {e}") from e
    finally:
        winreg.CloseKey(key)
