# 文档

文档分两层，各有明确职责，互不重复：

| 层 | 位置 | 职责 | 生命周期 |
|----|------|------|---------|
| **参考** | `ARCHITECTURE.md` / `CONFIGURATION.md` | 项目构成、模块分层、数据流、配置项。回答「系统长什么样、有哪些开关」 | 长期，随结构变更同步 |
| **规范** | `standards/` | 检查标准、跨语言契约、扩展方式、运行时 UX 硬约束。回答「怎么改才对」 | 长期，是评审依据 |

变更历史不在文档里，在 [CHANGELOG.md](../CHANGELOG.md)。
上手与贡献流程见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 参考

- [ARCHITECTURE.md](ARCHITECTURE.md) — 项目构成图、管线流程、生成器模块依赖、Provider 体系、
  运行时分层 / 帧内流水线 / 状态机 / 拖动时序 / Overlay UI（全部 mermaid）。
- [CONFIGURATION.md](CONFIGURATION.md) — Python `Settings` 字段、环境变量、CLI 参数，
  以及运行时 `config.rs` 调参面。

## 规范

| 文档 | 用途 |
|------|------|
| [standards/CODE_QUALITY_GATES.md](standards/CODE_QUALITY_GATES.md) | 提交前必须通过的检查、测试分层与测试铁律 |
| [standards/GENERATOR_RUNTIME_CONTRACT.md](standards/GENERATOR_RUNTIME_CONTRACT.md) | Python ↔ Rust 唯一强耦合契约（单一事实源） |
| [standards/EXTEND_ACTIONS.md](standards/EXTEND_ACTIONS.md) | 扩展动作（新增一个动画）的完整清单 |
| [standards/EXTEND_MECHANISMS.md](standards/EXTEND_MECHANISMS.md) | 扩展机制：体型 / Provider / 管线阶段 / 运行时系统与输入面 |
| [standards/EXTEND_PROMPTS.md](standards/EXTEND_PROMPTS.md) | 扩展与调优提示词 |
| [standards/RUNTIME_UX.md](standards/RUNTIME_UX.md) | 运行时交互与 UI 规范（含 ASCII-only 字体硬约束） |

## 维护约定

1. **先文档，后代码**：改动跨语言契约或 UI 硬约束时，先更新对应规范文档，再改实现。
2. **规范可执行**：每条规范尽量绑定一个自动化守护（测试或检查命令），文档里注明是哪一个。
3. **不留过期文档**：结论失效就删或改，不留半失效的文档；一次性的调查过程写进 PR 描述，
   只把长期有效的结论沉淀到这里。
4. **文档只引用仓库内路径**：不出现指向本仓库之外的相对路径或特定机器的绝对路径。
