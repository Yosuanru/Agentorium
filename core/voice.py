"""语音输入：用 Windows 自带的语音识别，不装任何东西。

本机装了 `zh-CN · Microsoft Speech Recognizer 8.0`，走 PowerShell 的
`System.Speech` 就够——不需要 whisper、不需要联网、不需要 pip 装包。

**两个坑（都踩过）：**

1. 脚本**不能写成 .ps1 再跑**——这台机器的 PowerShell 执行策略不允许执行脚本文件
   （报 `UnauthorizedAccess`）。要绕过就得加 `-ExecutionPolicy Bypass`，
   那是削弱机器的安全设置，得作者本人点头才该做。所以改成**内联命令**：不从文件读，
   策略就管不着，也不用改任何设置。
2. 内联命令**必须是单行**。多行脚本当参数传给 `powershell -Command` 时，
   会被 Windows 的命令行引号规则拆散，PowerShell 报的是「$r = New-Object System…」这种
   莫名其妙的脚本解析错。
3. 输出走的是控制台代码页（本机 GBK），按 UTF-8 读会抛 UnicodeDecodeError。

代价是**准确率一般**（系统自带的那套就这样）。定位很清楚：**说话是为了快，不是为了准**
——出来的是草稿，在输入框里改两个字就能发。要更高准确率得本地跑 whisper，
那是另一个量级的体积和依赖。
"""
from __future__ import annotations

import os
import subprocess

# 单行；顺序不能动。用 ; 分隔，避免任何换行。
SCRIPT = (
    "try {"
    " Add-Type -AssemblyName System.Speech;"
    " $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine"
    "([System.Globalization.CultureInfo]'zh-CN');"
    " $r.SetInputToDefaultAudioDevice();"
    " $r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar));"
    " $res = $r.Recognize([TimeSpan]::FromSeconds(__SECONDS__));"
    " if ($res) { Write-Output $res.Text };"
    " $r.Dispose()"
    " } catch { Write-Error $_.Exception.Message; exit 2 }"
)


def listen(seconds: int = 10) -> str:
    """听一段，返回识别到的文字。失败时抛 RuntimeError（带人话原因）。"""
    script = SCRIPT.replace("__SECONDS__", str(int(seconds)))
    kwargs: dict = {"capture_output": True, "timeout": seconds + 40}
    if os.name == "nt":
        # 面板是 console=False 打的包：不设这个，点一次「说」就跟着弹一个
        # PowerShell 黑窗——和 claude 子进程那个是同一个病根。
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            **kwargs,
        )
    except FileNotFoundError:
        raise RuntimeError("这台机器上没有 PowerShell，语音输入用不了。") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("语音识别没在预期时间内返回。") from None

    text = _decode(p.stdout)
    if p.returncode != 0 and not text:
        err = [ln for ln in _decode(p.stderr).splitlines() if ln.strip()]
        raise RuntimeError("语音识别起不来：%s" % (err[-1][:120] if err else "未知原因"))
    return text


def _decode(raw: bytes) -> str:
    """PowerShell 的输出走控制台代码页（本机是 GBK），不能一律当 UTF-8 读。"""
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc).strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace").strip()
