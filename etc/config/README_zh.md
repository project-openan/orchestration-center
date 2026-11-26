# 模型配置

模型定义放在 `etc/config/models.yaml`，该文件被 Git 忽略——从
[`models.yaml.example`](models.yaml.example) 复制一份开始。密钥不写在该文件里：
字段填写的是**保存该值的环境变量名**。本地示例见
[`.env.example`](../../.env.example)。修改后需重启进程。

`LLM_CONFIG_FILE` 可指定其他模型文件（相对路径以仓库根目录为基准）。
Docker Compose 通过 `LLM_CONFIG_HOST_FILE` 挂载模型文件。

`models:` 下的每个键是一种能力（`chat`、`embed`、`rerank`，或由已注册协议
Profile 支持的其它名称）。`model` 与 `url` 必填；`provider` 默认 `openai_compatible`（`openai` 是兼容别名）
（兼容 OpenAI 请求/响应格式），`aoc_signed` 增加 AOC 签名。可选项有
`description`、`timeout`（正数秒）、`verify_ssl`、`enable_thinking`。聊天 Profile 还支持
`stream`、`stream_total_timeout`（正数秒，默认 600）、`proxy` 和添加厂商选项的
`extra_body`；后者禁止覆盖 model/messages 等协议输入及 stream 开关。
embed/rerank 不能启用聊天 SSE；断流、截断按失败处理，不返回残缺答案。
详见 [SPG/模型流式配置](../../docs/zh/SPG导入.md)。

```yaml
models:
  chat:
    provider: openai_compatible
    model: your-model
    url: https://provider.example/v1/chat/completions
    api_key_env: LLM_CHAT_API_KEY
  embed:
    provider: aoc_signed
    model: your-embedding-model
    url: https://gateway.example/embeddings
    auth:
      app_key_env: LLM_EMBED_AUTH_APP_KEY
      app_secret_env: LLM_EMBED_AUTH_APP_SECRET
```

`api_key_env` 以及所有 `*_env` 字段填的是环境变量名；直接把密钥写进文件会被
拒绝。`api_key_env` 可省略，本地无鉴权端点因此不需要它。AOC 签名还接受
`authorization_env`，以及字面量 `api_code`、`api_version`、`scenario_code`、
`scenario_version`、`ability_code`、`test_flag`。

`common/llm/config/model_sources.py` 承载版本化请求/响应模板。同协议换模型
无需修改 Python；换协议则需按 `provider` 中使用的名称注册并测试新 Profile。
不要记录请求头、请求体或凭据。

模型设置仍在 `.env` 里的存量部署，可运行
`python -m scripts.migrate_llm_config`。工具会写出 `models.yaml`，在改动任一
文件前先验证全部 Profile 与密钥引用，把密钥值留在 `.env`，且不输出密钥。
旧 JSON 模型文件已不再被跟踪或读取。

如果存量部署只有 `common/config/llm_config.json`，改运行
`python -m scripts.migrate_legacy_llm_json`：密钥进入 `.env`，非敏感模型定义
进入 `models.yaml`。自定义旧请求模板须先实现相应的协议 Profile。
