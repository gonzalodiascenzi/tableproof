# framework de ventures

motor compartido y una carpeta por emprendimiento.

- `framework/`: la plantilla (`framework-emprendimiento.md`) y el checklist de whatsapp (`whatsapp-checklist.md`).
- `ventures/<slug>/venture.md`: un emprendimiento, a partir de `export/podium.json` de seedproof (por URL o archivo local). todavía no hay ninguno: el podio de seedproof está vacío.
- `ventures/_archivo/`: casos descartados. `scamproof` está archivado: ver su motivo al inicio de su archivo.
- reglas: `CLAUDE.md`.

## motor del respondedor (prompt 5)

- `engine/flow.py`: esquema de `flow.yaml` (documentado en el docstring) y validador. Falla si un estado no tiene salida a humano, si hay transiciones huérfanas o estados inalcanzables, y si una palabra clave es un booleano de yaml (poné `"no"` entre comillas).
- `engine/responder.py`: máquina de estados. El motor, no el flow, hace cumplir: aviso de asistente automático en el primer mensaje, salida a humano en cualquier estado, baja inmediata, ventana de 24 h y opt-in con fecha.
- `engine/store.py`: estado y eventos en sqlite.
- `engine/simulator.py`: `python -m engine.simulator <flow.yaml>` para conversar sin conectar nada (`/avanzar 25` corre el reloj, `/optin`, `/seguimiento <plantilla>`).
- tests: `python -I -W ignore -m unittest discover -s tests -t .`. El flow de `tests/fixtures/` es ficticio; no hay flow de ningún emprendimiento real todavía.
- [hipótesis] el primer mensaje del cliente habilita responderle dentro de la ventana; los mensajes iniciados por la empresa exigen un opt-in explícito. Contrastar con la política de meta antes de lanzar.
