# Configuración de Google Sheets

La aplicación utiliza Google Sheets como base de datos y ya no necesita Supabase.

## 1. Preparar Google Cloud

1. Crea o selecciona un proyecto en Google Cloud.
2. Habilita **Google Sheets API** y **Google Drive API**.
3. Crea una **cuenta de servicio** y descarga su clave JSON.
4. Crea una planilla vacía de Google Sheets.
5. Comparte la planilla como **Editor** con el correo `client_email` de la cuenta de servicio.
6. Copia el identificador que aparece entre `/d/` y `/edit` en la URL de la planilla.

## 2. Configurar Streamlit Secrets

En Streamlit Cloud abre **App > Settings > Secrets** y agrega:

```toml
GSHEET_ID = "ID_DE_LA_PLANILLA"
ADMIN_PASSWORD = "TU_CLAVE_ADMINISTRATIVA"

[gcp_service_account]
type = "service_account"
project_id = "tu-proyecto"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "cuenta-servicio@tu-proyecto.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

No publiques la clave JSON ni los Secrets en GitHub.

## 3. Primera ejecución

Al iniciar la aplicación se crean automáticamente estas pestañas:

- `establecimientos`
- `contratos`
- `planes`
- `plan_trabajo`

También se cargan los establecimientos iniciales de la Red SSMOCC cuando la pestaña `establecimientos` se crea por primera vez.

## 4. Verificación

- El dashboard debe abrir sin un error de conexión.
- El acceso `?admin=1` debe aceptar `ADMIN_PASSWORD`.
- Guardar un contrato debe crear o actualizar una fila en `contratos`.
- Publicar el Anexo N°1 debe actualizar `plan_trabajo` y agregar un registro en `planes`.
