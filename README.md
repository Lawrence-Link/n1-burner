# N1 Burner

N1 Geiger Counter 计数器固件烧录工具。

> 本项目全程使用 AI vibe coding 完成 🤖

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 启动程序

```bash
python main.py
```

### 首次使用（重要）

**首次给新设备烧录固件时，必须按以下步骤操作：**

1. ✅ 勾选"首次烧录 (First Burn)"
2. ✅ 建议 Bootloader 选择"Use default 使用默认"
3. ✅ 建议 Partition Table 选择"Use default 使用默认"
4. ✅ 勾选"Burn eFuse - DIS_PAD_JTAG (烧录熔丝位 - 禁用 JTAG)"
5. 选择固件文件
6. 选择串口
7. 点击 Burn Firmware

⚠️ **注意**：eFuse 烧录操作是不可逆的，会永久禁用 JTAG 调试功能，但是解放引脚占用对于烧录此固件而言是必要的。

### 后续更新固件

后续只需要更新固件时：

1. **无需勾选**"首次烧录 (First Burn)"
2. 选择固件文件
3. 选择串口
4. 点击 Burn Firmware

## 项目结构

```
n1-burner/
├── main.py                      # 主程序
├── requirements.txt             # Python 依赖
├── README.md                    # 说明文档
├── res/                         # 资源文件夹
│   └── bg.png                   # 背景图片
├── bootloader_default/          # 默认 bootloader
│   └── bldr.bin
└── partition_table_default/     # 默认分区表
    └── table.bin
```

## 细节

- 目标设备：N1 Geiger Counter
- 目标芯片：ESP32-C6
- 波特率：460800
- 烧录地址：
  - Bootloader: `0x0`
  - Partition Table: `0x8000`
  - Firmware: `0x10000`

---

## <a target="_blank" href="https://icons8.com/icon/wLgsZitlWmzO/installing-updates">Installing Updates</a> icon by <a target="_blank" href="https://icons8.com">Icons8</a>