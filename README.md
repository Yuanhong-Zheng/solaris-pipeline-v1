# Solaris Blender 建模 Pipeline v1

这是当前版本的独立归档。它记录的流程是：GPT-6 Astra 根据两位玩家的首帧图像、任务指令和动作可视化图输出结构化的初始场景规格；本地 Blender 规则脚本读取这些规格和原始动作序列，创建共享的简化三维世界，驱动两个人物并由 Blender CPU 渲染。

Astra 在这个版本中不生成 Blender Python 代码，也不生成逐帧人物动作。人物运动由 `motion.py` 根据输入动作序列和固定的 Minecraft 风格运动规则计算；地面、天空、云朵、地标、人物几何体和放置方块由 `render_solaris_scene.py` 的规则逻辑创建。

## 归档内容

- `astra_generate_specs.py`：调用 GPT-6 Astra 并规范化场景规格。
- `scene_specs.json`：本版本默认使用的 Astra 场景规格快照。
- `scene_specs_astra_builder.json`：同一份 Blender 构建规格的明确命名副本。
- `astra_scene_specs.json`：包含 Astra 原始响应文本和审计信息的快照。
- `prepare_inputs.py`、`inputs/`：首帧图像、动作条件和来源记录。
- `render_solaris_scene.py`、`motion.py`：Blender 场景构建和动作模拟。
- `run_pipeline.py`、`render_all.sh`：渲染、编码、视频验证和页面发布流程。
- `publish_viz.py`、`web/`、`check_web.cjs`：可视化页面构建及功能检查。

本归档不重复复制原始 Solaris 数据集、Blender 可执行文件或已经生成的视频；当前 Astra 结果仍保存在 `../gpt_blender/outputs_astra/`，页面发布目录为 `../../viz-hub/drops/solaris-gpt-blender-astra/`。

## 运行位置

在本目录执行即可使用同一套 Solaris 根目录依赖：

```bash
./render_all.sh --jobs 2 --force \
  --spec-file scene_specs_astra_builder.json \
  --output-root outputs_astra \
  --site /ytech_m2v8_hdd/workspace/kling_mm/zhengyuanhong/viz-hub/drops/solaris-gpt-blender-astra
```

渲染环境仍为 Blender Workbench + CPU/Mesa `llvmpipe`，输出规格为 20 fps、257 帧、1280×704。运行 Astra 规格生成器时通过临时环境变量提供 `ZCLOUD_API_KEY`，密钥不保存在此归档中。
