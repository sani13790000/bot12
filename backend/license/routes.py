backend/license/routes.py
Phase 6 License API routes

Customer endpoints:
  POST /license/heartbeat
  POST /license/device/register
  DELETE /license/device/{id}
  GET  /license/my
  GET  /license/features

Admin endpoints:
  POST /admin/license/create
  POST /admin/license/activate
  POST /admin/license/suspend
  POST /admin/license/revoke
  POST /admin/license/resume
  GET  /admin/license/{hash}
  GET  /admin/license/{hash}/audit
  GET  /admin/license/stats
