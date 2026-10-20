# Antislop MCP

Antislop MCP gives coding agents a local editor that makes audience-facing prose more specific and less like generic AI output. It is an MCP server for [Qwen3.8-27B-antislop](https://huggingface.co/AlexWortega/Qwen3.8-27B-antislop) that exposes two tools:

- `antislop_status` checks the local model endpoint.
- `antislop_rewrite` rewrites or continues prose while preserving requested terms.

This project has two separate pieces:

| Piece | Role |
| --- | --- |
| MCP server | The agent-facing stdio process that exposes Antislop tools. |
| macOS app | The local runtime that loads the model, owns the runner, and provides menu-bar controls. |

The agent talks to the MCP server, and the MCP server talks to the macOS app when you use the bundled local runtime.

## MCP server for agents

The MCP adapter does not load model weights. Run Antislop behind any OpenAI-compatible local server. The model card documents vLLM:

```bash
uv venv
source .venv/bin/activate
uv pip install -e .

vllm serve AlexWortega/Qwen3.8-27B-antislop \
  --served-model-name antislop \
  --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --max-model-len 32768
```

For a different endpoint:

```bash
export ANTISLOP_BASE_URL=http://127.0.0.1:1234/v1
export ANTISLOP_MODEL=Qwen3.8-27B-antislop
export ANTISLOP_API_KEY=local
```

### Connect an agent

The server uses MCP over stdio, so clients start the `antislop-mcp` executable as a local subprocess. Use an absolute path in client configuration when possible.

#### Codex

```bash
codex mcp add antislop -- "$PWD/.venv/bin/antislop-mcp"
codex mcp list
```

Start a new Codex conversation after registering the server. Ask Codex to use Antislop explicitly, or add the agent guidance below to your project instructions.

#### Claude Code

```bash
claude mcp add --scope user --transport stdio antislop -- \
  "$PWD/.venv/bin/antislop-mcp"
claude mcp list
```

Claude Code can use both tools directly. The MCP server does not install policy or skills into Claude Code, so add this to your project instructions if you want consistent use:

```text
Use the antislop_rewrite MCP tool for drafts and prose intended for other people.
Do not use it for ordinary conversation, code, or progress updates. Preserve
names, numbers, URLs, and technical terms, and review every returned rewrite.
```

#### Claude Desktop

Merge this entry into `~/Library/Application Support/Claude/claude_desktop_config.json`, preserving any existing servers, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "antislop": {
      "command": "/absolute/path/to/antislop-mcp/.venv/bin/antislop-mcp"
    }
  }
}
```

Claude Desktop will see `antislop_status` and `antislop_rewrite` as tools. The menu-bar app can open automatically when the first tool call arrives.

#### OpenCode

```bash
opencode mcp add antislop --global -- \
  "$PWD/.venv/bin/antislop-mcp"
opencode mcp list
```

Or add it to `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "antislop": {
        "type": "local",
        "command": ["/absolute/path/to/antislop-mcp/.venv/bin/antislop-mcp"]
      }
    }
  }
}
```

Other MCP clients can use the same stdio command: `/absolute/path/to/antislop-mcp/.venv/bin/antislop-mcp`.

`antislop_rewrite` supports `polish`, `humanize`, and `continue` modes. It returns the original text on endpoint failure, and rejects output that drops terms listed in `preserve`. These checks cannot prove factual or semantic fidelity; review the result before publishing.

### Guidance for agents

Use `antislop_rewrite` for text intended for other people: documents, messages, product copy, release notes, website copy, and other audience-facing prose. Preserve names, numbers, URLs, technical terms, and formatting with the `preserve` field when they must remain exact.

Do not use it for ordinary assistant replies, code, factual verification, or progress updates. The tool is on demand; it does not automatically rewrite every response. Review every returned rewrite for meaning, tone, and factual accuracy.

### Long inputs and timeouts

Local generation is much slower than hosted inference. On a large rewrite, the model may spend several minutes producing a response even though it is healthy. Antislop uses these defaults:

| Setting | Default | Purpose |
| --- | ---: | --- |
| Model request timeout | 240 seconds | Time allowed for `llama-server` to finish one generation. |
| MCP socket timeout | 300 seconds | Time allowed for the MCP adapter to receive the app response. |
| One-shot rewrite limit | 1,200 words | Largest `polish` or `humanize` request accepted without chunking. |

Requests over 1,200 words return `needs_chunking` immediately with the original text and instructions for splitting it. Agents should split long documents at heading or paragraph boundaries, rewrite each section separately, and reassemble the accepted sections without changing their separators. `continue` mode is exempt because its input is context rather than text that must all be reproduced.

The limits can be adjusted with `ANTISLOP_TIMEOUT`, `ANTISLOP_MCP_TIMEOUT`, and `ANTISLOP_MAX_WORDS`. MCP clients may also impose their own tool-call timeout, so smaller sections remain more reliable than one very long generation.

## macOS menu-bar app

The bundled macOS app is the local model runtime, not another agent-facing interface. It owns the runner, exposes a private Unix socket to the MCP server, and provides menu-bar controls for loading or unloading the model. You can also run the MCP server against another OpenAI-compatible endpoint without using the app.

This requires macOS, Apple Silicon, Xcode Command Line Tools, a local Python environment, and a compatible OpenAI-style runner such as `llama-server`:

```bash
uv venv
uv pip install -e .
python scripts/build_app.py --output build/Antislop.app --python "$PWD/.venv/bin/python"
python scripts/install.py --app build/Antislop.app --python "$PWD/.venv/bin/python" \
  --request-timeout 240 --runner \
  llama-server -hf rawmodels/Qwen3.8-27B-antislop-GGUF:Q4_K_M \
  --alias antislop --host 127.0.0.1 --port 8000 --jinja \
  --reasoning-budget 0 --no-reasoning-preserve
open "$HOME/Applications/Antislop.app"
```

After the app is installed, connect your agent using the client instructions above. The MCP server remains the agent-facing process; the app only supplies the local model runtime.

The MCP adapter opens `Antislop.app` if the socket is not available. Model output and service diagnostics are written to `~/Library/Application Support/Antislop/runner.log` and `controller.log`; drafts are not logged by the controller.

The runner command is configurable in `~/Library/Application Support/Antislop/config.json`, so you can replace `llama-server` with an MLX or LM Studio-compatible server later.

### Using Antislop from Codex

Once the menu-bar app says `Ready`, ask Codex to use the MCP tool explicitly:

```text
Run Antislop on your proposed launch announcement. Preserve the product name,
the date, and every number. Return only the revised announcement.
```

Other useful requests:

```text
Rewrite this email with Antislop. Keep the tone warm but direct, and preserve
all names, dates, URLs, and commitments:

<paste draft here>
```

```text
Use Antislop in `polish` mode on this product description. Keep the structure,
technical terms, and Markdown formatting, but remove generic AI phrasing.
```

```text
Use Antislop in `continue` mode to finish this paragraph naturally. Match the
existing voice and do not repeat the last sentence:

<paste unfinished paragraph here>
```

The app does not rewrite every Codex response automatically. It is an on-demand
MCP tool for drafts and other text you intend to share. The menu-bar controls
let you keep the model loaded, unload it to release memory, open logs, or quit
the service.

### Menu-bar controls

| Ready and enabled | Disabled and unloaded |
| --- | --- |
| ![Antislop menu-bar app ready](docs/images/antislop-ready.png) | ![Antislop menu-bar app off](docs/images/antislop-off.png) |

### Troubleshooting

- If a client reports that the server is unavailable, check that the configured executable exists and is executable: `ls -l .venv/bin/antislop-mcp`.
- If the app menu stays on `Loading model`, inspect `~/Library/Application Support/Antislop/runner.log` and wait for the local runner to finish loading its weights.
- If a rewrite times out, split it into smaller sections before increasing the timeout. For consistently slow hardware, reinstall with a larger `--request-timeout` and set `ANTISLOP_MCP_TIMEOUT` to a slightly higher value in the MCP client environment.
- If the app is disabled, enable it from the menu bar before retrying. Disabling the app stops the model runner and releases its memory.
- If you change the runner command, rerun `scripts/install.py` or edit `~/Library/Application Support/Antislop/config.json`, then restart `Antislop.app`.
- The service is local-only by default. The agent client still receives the draft and tool result, so client-side cloud and retention settings remain applicable.

## Development

```bash
uv run pytest -q
uv run ruff check src tests
```
