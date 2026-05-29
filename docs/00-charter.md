# 00 — Project charter: Intelbras AMT 8000 → Home Assistant

## Hipótese central

O AMT 8000 usa o mesmo protocolo `0xe7` nativo (TCP 9009) já confirmado nos modelos AMT 1016 NET e AMT 2018 NET, para o qual existe `tarikbc/ha-intelbras-alarm` como referência funcional. A integração HA será uma adaptação desse projeto com extensões para controle de partições e leitura de zonas individuais — funcionalidades documentadas no protocolo mas não implementadas pelo projeto de referência.

## Escopo

### Dentro
- Armar / desarmar o sistema inteiro
- Armar / desarmar partições (grupos) individualmente
- Status em tempo real de cada zona (aberta / fechada / em alarme)
- Notificações de alarme via HA (evento HA + automação iOS)
- Comunicação 100% local (LAN), sem dependência de cloud Intelbras em runtime

### Fora
- Controle de PGMs (pode ser adicionado em iteração futura)
- Histórico de eventos / log do painel
- Acesso via cloud / GPRS / módulo celular
- Abertura física do equipamento (sem UART/JTAG)
- App repackaging / root do Android

## Critérios de sucesso

### MVP
- Entidade `alarm_control_panel` no HA refletindo o estado arm/disarm do AMT 8000 em tempo real
- Comandos arm / disarm executados com confirmação de estado
- `binary_sensor` por zona mostrando aberta / fechada
- Evento HA disparado quando o alarme é acionado (sirene ativa)

### Aceitável-parcial
- Se partições individuais forem inacessíveis: arm/disarm global apenas
- Se zonas individuais forem inacessíveis via protocolo: apenas estado global de alarme

### Failure modes que encerram o projeto
- AMT 8000 usa protocolo completamente diferente do 0xe7 (descartado por evidência de recon)
- Firmware exige autenticação por certificado ou secure element (improváveis para modelos NET)
- Panel não responde na porta 9009 e nenhuma outra porta produz handshake reconhecível

## Princípios de execução

1. **Documentar tudo no journal.** Mesmo falhas.
2. **Não comitar dados sensíveis.** IP local, senha do painel, MAC — tudo redacted antes de qualquer push.
3. **LAN-first.** Zero dependência de cloud em runtime.
4. **Protocolo 0xe7 como ponto de partida.** Não reinventar — adaptar o projeto de referência.
5. **Confirmar antes de escalar.** Revisão a cada gate do playbook.

## Arte prévia

- `tarikbc/ha-intelbras-alarm` — integração HA funcional para AMT 1016/2018 NET com protocolo 0xe7 documentado:
  - Auth, arm/disarm global, PGMs 1-2, binary sensors
  - Protocolo de discovery de zonas documentado mas **não implementado** (marcado como "Future Enhancement")
  - Parsing do byte 19 para live-siren vs. memory bit (documentado e implementado)
- Protocolo 0xe7 completamente documentado em `INTELBRAS_PROTOCOL_DOCUMENTATION.md` no repo acima

## Roadmap

| Fase | Objetivo | Tempo estimado |
|------|----------|----------------|
| 1 | Recon de rede (nmap, fingerprint porta 9009) | 30 min |
| 3a | Validar auth + status no AMT 8000 com script Python | 2–4 h |
| 3b | Mapear partições e zonas no AMT 8000 | 4–8 h |
| 4 | Componente HA completo (fork do projeto de referência) | 8–16 h |

> Fase 2 (PCAPdroid / JADX) **pulada** — protocolo já documentado pelo projeto de referência.
> Só voltamos à Fase 2 se o AMT 8000 apresentar respostas incompatíveis com o esperado.

## Decisão de Go/No-Go após Phase 1

- ✅ Porta 9009 responde com magic `e7` → Phase 3 direto
- ⚠️ Porta 9009 aberta mas resposta diferente → investigar variante do protocolo
- ❌ Porta 9009 fechada e nenhum outro indício → Phase 2 (PCAPdroid com app AMT Remoto)
