"""Regresi: LocalProvider mengirim max_tokens (cegah loop pengulangan sampai timeout)."""
from unittest import mock
from google.genai import types
from ai.providers.local_provider import LocalProvider

def _payload(**kw):
    p = LocalProvider(system_prompt="s", model_name="m", **kw)
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    with mock.patch("ai.providers.local_provider.requests.post", return_value=resp) as post:
        p.generate([types.Content(role="user", parts=[types.Part(text="hi")])])
    return post.call_args.kwargs["json"]

results = [
    ("max_tokens terkirim bila di-set", _payload(max_tokens=1024).get("max_tokens") == 1024),
    ("default None -> tidak dikirim (perilaku lama)", "max_tokens" not in _payload()),
    ("0 = tanpa batas", "max_tokens" not in _payload(max_tokens=0)),
]
failed = 0
for name, ok in results:
    print(("✅" if ok else "❌"), name); failed += (not ok)
print(f"Total: {len(results)} | Failed: {failed}")
raise SystemExit(1 if failed else 0)