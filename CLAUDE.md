# reglas del proyecto

- todo dato en docs es [verificado] con fuente y fecha, o [hipótesis]. nunca presentar una hipótesis como hecho.
- secretos solo por variables de entorno. `.env.example` sin valores reales. `.gitignore` excluye `.env`.
- nunca commitear datos de clientes, capturas ni materiales de clientes.
- los umbrales de corte, el presupuesto y el precio los pone el dueño; no los inventes.
- un repo con un motor compartido y una carpeta por emprendimiento: `ventures/<slug>/`. los descartados van a `ventures/_archivo/`.
- no crear ni publicar repos remotos: lo hace el dueño.
