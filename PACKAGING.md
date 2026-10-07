# 打包成 Windows 便携版

只有需要"不装 Python、直接双击运行"时才用它。**平时源码运行就够了**（见 `README.md` 第四节）。

## 步骤

```bash
pip install -r requirements-build.txt
python -m PyInstaller agentorium.spec --noconfirm --distpath dist --workpath _build
```

产物在 `dist/Agentorium/`。

## 两个坑

1. **打包前先关掉正在运行的实例。** 否则 PyInstaller 删不掉 `dist/Agentorium/_internal/`
   里被进程锁着的 DLL，报 `PermissionError: [WinError 5]`。
2. **`dist/` 是整个移走、别原地覆盖。** 半新半旧的产物**不会报错**，只会莫名其妙。

## 验收标准

**打了包、并且在 exe 里真跑通一次。**
"单元测试过了"和"代码里看着对"都只是必要条件，不是充分条件。
