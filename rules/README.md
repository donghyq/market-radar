# 证据规则库使用说明

将根目录下的 `rules/` 整体复制到其他工具即可复用。规则放在 `evidence_rules.json`，执行器是 `engine.py`，只使用 Python 3.11 标准库并读写 UTF-8 JSONL。

```sh
python rules/engine.py input.jsonl --output output.jsonl
```

示例输入，每行一条记录：

```jsonl
{"id":"p1","platform":"V2EX","record_type":"signal","thread_id":"1","title":"求一个好用的记账工具","source_url":"https://example.test/t/1"}
{"platform":"V2EX","record_type":"comment","thread_id":"1","comment_id":"2","parent_url":"https://example.test/t/1","source_url":"https://example.test/t/1#r_2","author_id":"3","content":"我做了个工具，私信我免费领安装包。"}
```

## 输入和输出

- `record_type` 为 `signal` 或 `comment`。提供 `platform` 或 `channel`，并保留采集到的 `id` 或 `comment_id`、`title`、`content`、`source_url` 和源站时间字段。`source_published_at` 和 `commented_at` 接收带时区的 ISO 8601 时间。
- 在同一批次提供上下文。原帖和评论通过同平台的 `thread_id` 关联，或通过评论的 `parent_url` 匹配原帖的 `source_url`。有明确引用时提供 `reply_to_id`，有源站稳定作者 ID 时提供 `author_id`。App Store 可提供评价对应的 `app_version`。同一作者跨帖重复的判定以本批记录为范围。也可提供已经保存的 `parent_text`。
- 输出按输入顺序保留 `schema_version`、`rule_version`、记录标识、来源字段、意图、标签、证据状态与 `matches`。每条命中记录规则 ID、来源和原文片段。评论的画像依据随 `profile_tags` 输出。
- 评论可同时输出多项 `intents` 和 `topic_tags`。例如同步失败可标为「同步异常」和「同步与备份」。`matches` 中的 `label` 和 `label_kind` 将标签对应到原文与来源。本地看板支持按评论意图、主题筛选，CSV 导出包含这两列。
- 用 `counts_as_demand` 筛出可用的需求证据记录。统计独立用户时可按平台和已知作者 ID 去重。`promotional` 表示明确推广，`unverified` 表示待复核，`context` 表示背景线索，`noise` 表示噪音。原文和来源随记录保留。

## 维护

修改 JSON 中的匹配条件时保留稳定的规则 ID，并递增 `rule_version`。意图规则可用 `platforms` 和 `record_types` 限定适用范围，用 `field` 指定匹配字段。需要上下文的回复可用 `parent_pattern` 检查原帖或被引用评论，命中后同时输出上下文来源。`exclude_pattern` 可去掉模板表达或推测性表述，再匹配对应规则。 [规则配置](evidence_rules.json)

主题规则放在 `comment_topics`。意图规则可设 `counts_as_demand: false`。仅命中这类规则时，修复确认、操作建议、更新说明和普通推荐以背景线索保留，仍可按标签检索。

小众软件论坛使用 `小众软件论坛` 或 `Appinn Forum`，保留主帖和回复关系。GitHub 使用 `GitHub Issues`，标题与正文可分别匹配，匹配时跳过 Markdown 引用、代码块和模板注释。使用 `--rules` 回放候选配置。 [0.2.1 开发计划](../docs/DEV_PLAN_0.2.1.md) · [扩充实测](../docs/TEST_PLAN_0.2.1.md#公开网络扩充实测)
