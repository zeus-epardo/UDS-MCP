# Memoria del equipo

Memoria compartida entre Zeus (creador) y Claude (cocreador). Claude no recuerda sesiones
anteriores: **este archivo es nuestra memoria**. Se carga en cada sesión a través de
`CLAUDE.md` y lo actualizamos al cerrar cada sesión.

> Es un repo público: aquí van métodos, decisiones y aprendizajes generales, nunca código,
> nombres internos ni datos de una empresa anterior.

## Ritual de sesión

- **Al empezar:** Claude lee este archivo y `git log --oneline -15` y resume en dos líneas
  dónde estamos y qué sigue.
- **Al cerrar:** Claude agrega la entrada en la bitácora, registra decisiones nuevas y
  actualiza los pendientes, y lo incluye en el último commit de la sesión.

## Quiénes somos

- **Zeus Epardo** — creador. Experto en diagnóstico automotriz (UDS, CAN, bancos de prueba).
  Decide el rumbo, valida en hardware y prioriza.
- **Claude** — cocreador. Diseña e implementa junto con Zeus, escribe tests y docs, y
  cuida que el README cuente la verdad.

## Cómo trabajamos

- Trabajamos directo en `main`, sin PRs. Una rama corta solo si algo es experimental.
- Commits convencionales; los de Claude llevan `Co-Authored-By`.
- Antes de cada commit: `ruff check . && ruff format --check . && pytest`.
- Todo se prueba primero en el bus virtual / simulador; el hardware se valida aparte.
- El README solo marca ✅ lo que funciona y está probado.
- No reimplementamos ISO-TP ni la codificación UDS: usamos `can-isotp` y `udsoncan`.
  Nuestro valor está encima: herramientas MCP, claim/release, clasificación, simulador,
  planes de prueba.

## Métodos de nuestra etapa anterior

Lo que Zeus recuerda de cómo trabajábamos y qué funcionaba, escrito en términos generales
para reconstruirlo aquí, mejor y sin límites.

### Los MCP que teníamos

Uno por bloque. Qué hacía cada uno y cómo lo recreamos en UDS-MCP.

| Nombre / rol | Qué aportaba | Cómo lo recreamos aquí | Estado |
|---|---|---|---|
| _(por llenar con Zeus)_ | | | |

### Prácticas y aprendizajes

- _(por llenar con Zeus)_

## Decisiones

| Fecha | Decisión | Por qué |
|---|---|---|
| 2026-10-27 | Proyecto clean-room, MIT, a partir de ISO 14229 / 15765 | Libre, open source y portafolio de Zeus; sin riesgo de propiedad intelectual ajena |
| 2026-10-27 | El core UDS se monta sobre `udsoncan` y `can-isotp` | Librerías maduras y MIT; nos enfocamos en la capa MCP |
| 2026-10-27 | Cada servicio devuelve un `UdsResult` (JSON, NRC con nombre) y nunca lanza excepciones UDS | Formato directo para las herramientas MCP |
| 2026-10-27 | Sin PRs: Zeus y Claude integran directo en `main` | Somos el equipo completo |

## Pendientes

- [ ] Decidir: configuración del simulador en el mismo TOML del ECU (`[sim]`) o en archivo aparte.
- [ ] Decidir: simulador y servidor MCP en pasos separados o juntos hasta la demo.
- [ ] Paso 3: simulador por software (`uds_mcp/sim/`) que reemplace a `tests/fake_ecu.py`.
- [ ] Paso 3: servidor MCP con FastMCP (stdio) y primeras herramientas.
- [ ] Llenar con Zeus la tabla de MCP y las prácticas de nuestra etapa anterior.

## Bitácora

### 2026-10-27

- Corregimos el correo de git: el commit del scaffold aparecía a nombre de otra cuenta.
- README honesto, `CLAUDE.md` y este `TEAM.md`; Claude agregado a los créditos.
- Core UDS: `UdsClient` (0x10, 0x11, 0x14, 0x19, 0x22, 0x27, 0x2E, 0x31, 0x3E y raw),
  cargador de configuración TOML, `open_bus()` y 26 tests en el bus virtual.
