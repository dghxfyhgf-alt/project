# Macau Navigation frontend

This Flutter app includes a generated Windows desktop runner under `windows/`.
From the repository root, use `start_backend.bat` on Windows to validate the
desktop prerequisites, start the FastAPI backend, and launch the app with:

```text
cd frontend
flutter run -d windows
```

The Windows client uses `http://127.0.0.1:8000`; Android emulators use
`http://10.0.2.2:8000`.
