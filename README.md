# 截图助手（JieTuZhuShou）

Windows 本地小工具：**截图识字 + 剪贴板历史**。全程离线，不联网、不上传。

## 📥 下载（普通用户）

**Windows 10 / 11 64 位 · 免安装版**

[**⬇ 下载 截图助手 v1.0.1**](https://github.com/zaonidaba-prog/jietuzhushou/releases/latest)

下载 zip 后解压，双击里面的 `截图助手.exe`。首次运行如遇 Windows SmartScreen 提示“未知发布者”，点“更多信息 → 仍要运行”。

> 也可以在 [Releases](https://github.com/zaonidaba-prog/jietuzhushou/releases) 页面查看历史版本。

## 功能

- 按 `Alt+Q`（可改）呼出截图：拖拽截局部，`Enter` 截整屏，`Esc` 取消。
- 截图自动保存到指定文件夹，自动用 RapidOCR 识别中英文，结果可编辑。
- 点「复制文字」才写入剪贴板；复制后自动进入剪贴板历史。
- 剪贴板历史监听系统剪贴板：文本、图片、文件都记录，永久保存在本机。
- 按 `Alt+V`（可改）打开历史：关键词搜索、类型筛选、收藏、重新复制。
- 托盘常驻、单实例、开机自启可开关。

## 快捷操作

| 操作 | 默认 |
|---|---|
| 截图识字 | `Alt+Q` |
| 打开剪贴板历史 | `Alt+V` |
| 截取整屏 | 呼出截图后按 `Enter` |
| 取消截图 | `Esc` |
| 历史里复制选中项 | 双击 / `Enter` |
| 历史里搜索 | `Ctrl+F` |

热键可以在托盘菜单 → 设置里修改。

## 数据位置

- 配置与数据库：`%APPDATA%\截图助手\`
- 剪贴板图片：`%APPDATA%\截图助手\clipboard_images\`
- 日志：`%APPDATA%\截图助手\logs\app.log`
- 截图：设置里指定的文件夹，默认 `图片\截图助手\`

## 开发运行

```powershell
.\.venv\Scripts\python.exe app.py
```

自检（截屏 + OCR）：

```powershell
.\.venv\Scripts\python.exe app.py --selftest
```

## 打包

```powershell
.\build.ps1
.\install.ps1
```

打包使用 PyInstaller，产物在 `dist\JieTuZhuShou\`。安装脚本会复制到
`%LOCALAPPDATA%\Programs\JieTuZhuShou` 并创建名为“截图助手”的桌面和开始菜单快捷方式。

## 说明

- 只能记录程序第一次运行之后的复制内容；程序未运行时不会记录。
- 剪贴板历史是本机 SQLite 明文存储，复制密码等敏感内容也会记录，可用托盘「暂停记录」或历史窗口删除。
- exe 未做数字签名，首次运行 Windows 可能提示“未知发布者”，选择“仍要运行”即可。

## License

本项目使用 [MIT License](LICENSE)。任何人都可以免费使用、修改、分发和商用，只需保留版权声明和许可证文本。
