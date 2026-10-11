# Phy-Engine 契约笔记（逆向自 dll_main.cpp / pe_sim.h / physicslab.h，2026-10-08 快照）

> 引擎版本：NetLogo-Mobile/Phy-Engine master（2026-10-07 克隆）。
> 本文是前端与引擎集成的**权威速查**。改引擎时同步更新。

## 1. WASM 导出面

`src/dll_main.cpp` 共 93 个 `extern "C"` 函数，`tools/build_wasm.sh` 用 rg 自动提取
全部导出（引擎加新 API 自动跟上）。分组：

- `pl_experiment_*`（实验管理）：create / destroy / load_from_string / load_from_file /
  save / dump / merge / add_circuit_element / connect / clear_wires / auto_layout /
  set_element_position / set_element_property_number / set_element_label / set_camera /
  set_element_xyz / set_xyz_precision
- `pl_pe_circuit_*`（仿真桥）：build / destroy / set_analyze_type / set_tr / set_ac_omega /
  analyze / digital_clk / sample_u8 / sample_layout / sample_digital_state_u8 /
  sync_inputs_from_pl / write_back_to_pl / write_back_to_pl_ex /
  set_model_digital / set_model_double_by_name / set_temperature / set_tnom
- `create_circuit* / circuit_* / analyze_circuit`（底层 netlist 直连，一般不用）
- `verilog_runtime_*`（Verilog 综合，芯片用）
- `phy_engine_last_error / clear_error / string_free`（错误通道：所有失败从这里拿信息）

**调用协议**：字符串入参为 UTF-8 指针；返回 `char*` 的（如 dump）必须用
`phy_engine_string_free` 释放。句柄类型都是 `void*`（js 侧存 number）。

## 2. .plsave 加载/保存格式（Unity 兼容）

```jsonc
{
  "Type": 0,                     // 0=电路（3=天体，4=电磁，不做）
  "CameraSave": "{...json 字符串}", // 含 VisionCenter/TargetRotation（pack_xyz 字符串）
  "StatusSave": "{...json 字符串}"  // 下述
}
// StatusSave:
{
  "Elements": [                  // 数组或 map（两种都吃）
    { "ModelID": "Resistor", "Identifier": "<33位随机串>",
      "Label": "定值电阻", "Position": "x,y,z", "XYZ": "...",
      "Properties": {...}, "Statistics": {...}, "IsBroken": false }
  ],
  "Wires": [ { "Source": "<Identifier>", "SourcePin": 0,
               "Target": "<Identifier>", "TargetPin": 1, "ColorName": "黑色" } ]
}
```

- **Position pack_xyz**：`"x,y,z"` 字符串，精度由 `pl_experiment_set_xyz_precision` 控制
- **element_xyz 网格**（unity 桌面格子）：`x_unit=0.16, y_unit=0.08, z_unit=0.1`，
  大元件 y 再 +0.045（`element_xyz::to_native / to_element_xyz`）
- 导线颜色名（parse_wire_color_name）：黑/蓝/红/绿/黄 → wire_color，默认蓝

## 3. 仿真流程（pl_pe_circuit_*）

```
exp = pl_experiment_load_from_string(sav)      // 或 create + add_element + connect
cir = pl_pe_circuit_build(exp)                 // 拓扑→引擎 netlist（含宏展开）
pl_pe_circuit_set_analyze_type(cir, 0|1|2|4)   // OP/DC/AC/TR（phy_engine_analyze_type）
pl_pe_circuit_set_tr(cir, dt, t_stop)          // 瞬态参数
pl_pe_circuit_analyze(cir)                     // 求解（同步）
pl_pe_circuit_sync_inputs_from_pl(cir, exp)    // Logic Input 状态同步（读"开关"属性）
pl_pe_circuit_digital_clk(cir)                 // 数字时钟步进（每帧调）
pl_pe_circuit_write_back_to_pl(cir, exp)       // 结果写回实验 JSON（见下）
s = pl_experiment_dump(exp)                    // 前端读 Statistics 驱动 UI
```

写回内容（write_back_to_pl_ec）：
- 一般元件：`Statistics.电压` / `Statistics.电流` / `Statistics.功率`（=U×I）
- Logic Output：`Properties.状态` = map_logic_output_state（高电平/低电平/X/Z）
- 元件属性读取：电阻 `"电阻"`、电容/电感同名、电池 `"电压"`、变压器变比 `"输入电压"/"输出电压"`

## 4. ModelID ↔ 引擎支持矩阵（pe_sim.h 权威）

### 4.1 模拟（1:1）
| ModelID | 引擎元件 | 属性 |
|---|---|---|
| Ground Component | 地（code 0 占位） | - |
| Resistor | RESISTOR | 电阻 |
| Basic Capacitor | CAPACITOR | 电容 |
| Basic Inductor | INDUCTOR | 电感 |
| Battery Source | VDC | 电压 |
| Simple/Push/Air Switch | SWITCH_SPST | 开关(0/1) |
| Transformer | TRANSFORMER | 输入电压/输出电压 |
| Mutual Inductor | COUPLED_INDUCTORS | 3 属性 |
| Rectifier | FULL_BRIDGE_RECTIFIER | - |

### 4.2 数字（1:1，PL pin 序 = 引擎 pin 序）
| ModelID | 引擎 | pins |
|---|---|---|
| Logic Input | DIGITAL_INPUT | [q]（状态属性"开关" 0/1） |
| Logic Output | DIGITAL_OUTPUT | [i]（写回"状态"） |
| Or/And/Nand/Nor/Xor/Xnor/Imp/Nimp Gate | 对应 | [ia,ib,o] |
| Yes/No Gate | YES/NOT | [i,o] |
| Schmitt Trigger | DIGITAL_SCHMITT? | [i,o] |
| Comparator | COMPARATOR(19) | [A,B,o]（属性 Ll,Hl） |
| JK Flipflop | DIGITAL_JKFF | [j,k,clk,q] |
| T Flipflop | DIGITAL_TFF | [t,clk,q] |
| Real-T Flipflop | DIGITAL_T_BAR_FF | [t_bar,clk,q] |
| Multiplier | DIGITAL_MUL2 | [a0,a1,b0,b1,p0,p1,p2,p3] |

### 4.3 宏展开（PL pin 序 ≠ 引擎序，pe_sim 有特判映射）
| ModelID | PL pins（前端必须按此序生成） |
|---|---|
| D Flipflop | 0=Q, 1=~Q（可选，未连自动加反相器）, 2=D, 3=CLK |
| Half Adder | 0=S, 1=C, 2=B, 3=A |
| Full Adder | 0=S, 1=Cout, 2=B, 3=Cin, 4=A |
| Half Subtractor | 0=D, 1=Bout, 2=B, 3=A |
| Full Subtractor | 0=D, 1=Bout, 2=B, 3=Bin, 4=A |
| Counter | 0..3=q3..q0, 4=clk, 5=en（未连时 en 自动接 1） |
| Random Generator | 0..3=q3..q0, 4=clk, 5=reset_n（未连时自动接 1） |

### 4.4 待补（引擎模型已存在，adapter 未接——下一个 PR）
- **8bit Input / 8bit Display**：引擎有 eight_bit_input.h/display.h（pins b7..b0）。
  pe_sim.h L263 报 "should be expanded by adapter" 但展开代码缺失。
  修法：build_from_ec 里加 1:1 pin_map[pl_id][i]→endpoint{e8, i}。
  PL prefab 的 8 pin 序以 catalog.json pins 数组为准。

### 4.5 引擎不支持（前端灰显/不进仿真）
Incandescent Lamp、LED（含彩色/双色）、Buzzer、Ammeter/Voltmeter/Multimeter/
Galvanometer/Microammeter/Electricity Meter/Resistance Box、Student Source、
Slide Rheostat、Current Source、Sinewave/Square/Triangle/Sawtooth/Pulse Source、
Relay(Element)、Transistor、P/N-MOSFET、Operational Amplifier、Spark Gap、
Tesla Coil、各类传感器、555 Timer。
> 引擎 include/model/models/ 下其实有 generator（方波/锯齿等）、linear（运放、
> 变压器中心抽头）、MOSFET 等，pe_sim 尚未映射——扩支持=照 4.1 样式加映射，
> 是提升完成度的最大杠杆。

## 5. 芯片 pin 视觉布局公式（Unity ChipComponent.OnPoolCreating）

芯片类（Pins 数组为空的 13 种）运行时生成 pin：

```
outputs: i ∈ [0, Outputs)   x=-0.065, y=0.02, z=lerp(-0.07,+0.07, i/(Outputs-1))   旋转(0,90,0)
inputs : i ∈ [Outputs, N)   x=+0.065, y=0.02, z=lerp(-0.07,+0.07, (i-Outputs)/(Inputs-1)) 旋转(0,90,0)
```
- **Outputs 在左、Inputs 在右**（门电路 prefab 相反：字面 pin 输入左/输出右，已提取）
- pin 文本：输出右侧对齐、输入左侧对齐，pin 名用 PL 约定名（见 4.3 表）
- 单输入/单输出时 Ratio=0.5

## 6. 数字 4 值逻辑

`PHY_ENGINE_D_L/H/X/Z`（0..3）。sample_digital_state_u8 每脚 1 字节。
前端显示：H→高电平绿、L→低电平灰、X/Z→警示色（Unity LevelDisplay 同语义）。

## 7. 坐标系与资产约定（前端渲染用）

- 引擎/Unity：LH，Y 上。three.js：RH，Y 上。统一 MIRROR_X 换轴
  （顶点 (−x,y,z)、四元数 (x,−y,−z,w)、翻转绕序）——GLB 已做好
- FBX 单位 cm（UnitScaleFactor=1）→ ×0.01 成米——GLB 已做好
- pin 世界位置 = GLB 节点矩阵（prefab 局部 TRS 已烘进 GLB node matrix）
- 桌面网格（element_xyz）：x 0.16 / y 0.08 / z 0.1 米每格
