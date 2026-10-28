# 私人 Notes

## 1. 按任务分流的开工前检查

统一入口 `run_preflight(task_type)`；失败即停止：

- 单纯回测：`PipelineConfig.load()` → `validate_for_read()` → `validate_manifests()` → `validate_point_in_time()`。
- 首次加载：`PipelineConfig.load()` → `validate_for_write()` → `DataLayout.create()` → `probe_source()` → `validate_contracts()`。
- 数据增量：`PipelineConfig.load()` → `validate_for_write()` → `load_checkpoint()` → `validate_continuity()` → `probe_source()`。

现有函数：配置与目录检查；其余函数为待实现设计。检查通过后才运行对应任务，写入成功、验证并登记 manifest 后才推进 checkpoint。
