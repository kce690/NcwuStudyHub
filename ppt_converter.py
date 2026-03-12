from __future__ import annotations

import platform
from pathlib import Path


def convert_ppt_to_pptx(src_ppt: Path, dst_pptx: Path, logger) -> bool:
    """
    在 Windows 环境通过本机 PowerPoint 将 .ppt 转换为 .pptx。
    失败时返回 False，不抛出异常到调用方。
    """
    if platform.system() != "Windows":
        logger.warning("当前系统不是 Windows，无法自动转换 .ppt：%s", src_ppt)
        return False

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        logger.warning("未安装 pywin32，无法转换 .ppt：%s", src_ppt)
        return False

    application = None
    presentation = None
    try:
        pythoncom.CoInitialize()
        application = win32com.client.DispatchEx("PowerPoint.Application")
        application.Visible = 1
        # 24 = ppSaveAsOpenXMLPresentation
        presentation = application.Presentations.Open(str(src_ppt), WithWindow=False)
        presentation.SaveAs(str(dst_pptx), 24)
        logger.info("转换成功：%s -> %s", src_ppt.name, dst_pptx.name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("转换失败：%s，错误：%s", src_ppt, exc)
        return False
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:  # noqa: BLE001
                pass
        if application is not None:
            try:
                application.Quit()
            except Exception:  # noqa: BLE001
                pass
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass
