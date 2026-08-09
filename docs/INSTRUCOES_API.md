# Referência da API

API REST do Sistema de Consulta Veterinária (v2).
Base URL local: `http://localhost:5000` — no deploy Docker, o nginx expõe os
mesmos endpoints sob `/api/` na porta `8000` (mesma origin do frontend).

Todos os endpoints devolvem JSON, exceto `/api/consulta/stream`, que devolve
Server-Sent Events (SSE). Qualquer pedido pode incluir o header `X-Session-Id`
para isolar o contexto de conversa entre utilizadores; se omitido, é gerado um
UUID por pedido.

O código está em [`backend/api/app.py`](../backend/api/app.py).

---

## GET `/api/status`

Health check. Confirma que a API está de pé e reporta o modelo/modo ativos.

```json
{
  "status": "online",
  "modelo": "qwen3:8b",
  "embed_model": "nomic-embed-text",
  "mode": "local",
  "version": "2.0.0",
  "timestamp": 1733347200.0
}
```

---

## POST `/api/consulta`

Pergunta síncrona — espera o pipeline terminar e devolve a resposta completa.

**Request**

```json
{ "pergunta": "Qual a dose do Senvelgo para gatos?" }
```

**Response**

```json
{
  "success": true,
  "resposta": "Segundo o documento, a dose indicada para gatos é 1 mg/kg.",
  "categoria": "medicamento",
  "entidades": {
    "termo_busca": "Senvelgo 15 mg/ml",
    "info_type": "dose",
    "especie_alvo": "gatos"
  },
  "via": "rules",
  "timings": { "classification": 0.001, "scraping": 2.4, "answer": 7.1, "total": 9.6 },
  "session_id": "alice-1"
}
```

`400 Bad Request` se o campo `pergunta` estiver ausente ou vazio.

---

## POST `/api/consulta/stream`

Mesma pergunta, mas com streaming SSE: envia logs em tempo real durante o
processamento e, no fim, a resposta. É o endpoint usado pela interface web para
mostrar o progresso.

Cada linha tem o formato `data: {json}\n\n`. O campo `type` identifica o evento:

| `type`      | Quando                                             |
|-------------|----------------------------------------------------|
| `start`     | Início do processamento (traz `session_id`)        |
| `log`       | Passo do pipeline (`level` + `message`)            |
| `heartbeat` | Mantém a ligação viva em passos longos             |
| `response`  | Resposta final (mesmos campos de `/api/consulta`)  |
| `error`     | Falha no pipeline (`message`)                      |
| `end`       | Fim do stream                                      |

```
data: {"type":"start","session_id":"alice-1","timestamp":1733347200.0}

data: {"type":"log","level":"INFO","message":"🔍 A classificar a pergunta...","timestamp":1733347201.0}

data: {"type":"response","message":"A dose indicada para gatos é 1 mg/kg.","categoria":"medicamento","entidades":{"termo_busca":"Senvelgo 15 mg/ml","info_type":"dose"},"timings":{"total":9.6},"via":"rules","timestamp":1733347210.0}

data: {"type":"end"}
```

---

## POST `/api/limpar_contexto`

Limpa o histórico de conversa de uma sessão (usado, por exemplo, ao iniciar uma
nova consulta na interface).

**Request** (o `session_id` pode vir no corpo ou no header `X-Session-Id`)

```json
{ "session_id": "alice-1" }
```

**Response**

```json
{ "success": true, "session_id": "alice-1" }
```

---

## Exemplos com `curl`

```bash
# Estado
curl http://localhost:5000/api/status

# Pergunta síncrona, com sessão nomeada
curl -X POST http://localhost:5000/api/consulta \
     -H "Content-Type: application/json" \
     -H "X-Session-Id: alice-1" \
     -d '{"pergunta": "Qual a dose do Senvelgo para gatos?"}'

# Pergunta com streaming (SSE)
curl -N -X POST http://localhost:5000/api/consulta/stream \
     -H "Content-Type: application/json" \
     -d '{"pergunta": "Medicamentos alternativos ao Dolocarp?"}'

# Reset do contexto
curl -X POST http://localhost:5000/api/limpar_contexto \
     -H "X-Session-Id: alice-1"
```

---

## Notas de produção

- **CORS** — em produção defina `CORS_ORIGINS` com os domínios reais (lista
  separada por vírgula), em vez do `*` de desenvolvimento.
- **Proxy** — no deploy Docker, o frontend e a API ficam na mesma origin e o
  nginx encaminha `/api/*` para a API. O SSE exige `proxy_buffering off`
  (já configurado em [`scripts/nginx.conf`](../scripts/nginx.conf)).
- **Servidor** — a API corre sob gunicorn (`gthread`, `API_WORKERS` workers,
  timeout 180 s). Ver [`Dockerfile`](../Dockerfile).
- **Sessões concorrentes** — cada `X-Session-Id` tem o seu próprio estado de
  conversa; sem esse header, cada pedido é tratado de forma isolada.
