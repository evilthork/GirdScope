# Publicar una versión de GridScope

## Esquema de versiones

- `0.7.1`: primera beta pública con la licencia no comercial definitiva.
- `0.7.2`: integración inicial de RaceRoom.
- `0.7.3`, `0.7.4`…: correcciones que no cambian el funcionamiento básico.
- `0.8.0`: nuevas funciones relevantes.
- `1.0.0`: primera versión considerada estable.

## Preparar los archivos

```powershell
.\scripts\crear-version-publica.ps1
```

El proceso ejecuta las pruebas y genera en `release\`:

- `GridScope-0.7.2-Windows.zip`
- `GridScope-0.7.2-Source.zip`

Ninguno contiene bases de datos, resultados, copias de seguridad, cachés,
credenciales o rutas personales.

## Probar una instalacion limpia

```powershell
.\scripts\probar-paquete-publico.ps1
```

La prueba descomprime el paquete de Windows en una carpeta temporal, utiliza
un perfil local aislado y confirma que GridScope crea una base vacia sin abrir
el navegador ni tocar los datos reales.

## Publicar en GitHub

1. Revisa `git status` y crea el commit de la versión.
2. Crea la etiqueta `v0.7.2`.
3. Sube la rama y la etiqueta al repositorio.
4. Abre **Releases → Draft a new release**.
5. Selecciona `v0.7.2` y marca la versión como **Pre-release**.
6. Adjunta ambos ZIP de `release\`.
7. Utiliza el contenido de `CHANGELOG.md` como notas de la versión.

Antes de subir, prueba el ZIP de Windows en una carpeta nueva y confirma que
el primer arranque solicita configurar el simulador.
