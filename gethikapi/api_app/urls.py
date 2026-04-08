from django.urls import path
from . import views

urlpatterns = [
    # ── Existing ──────────────────────────────────────────────
    path('', views.index, name='index'),
    path('logs-history/', views.logs_history, name='logs_history'),
    path('logs-json/', views.logs_json, name='logs_json'),
    path('download/', views.download_video, name='download'),
    path('stream/', views.stream_camera, name='stream_camera'),

    # ── Site Management ───────────────────────────────────────
    path('sites/', views.sites_list, name='sites_list'),
    path('sites/add/', views.sites_add, name='sites_add'),
    path('sites/<int:site_id>/delete/', views.sites_delete, name='sites_delete'),
    path('sites/<int:site_id>/toggle/', views.sites_toggle, name='sites_toggle'),

    # ── Notifications ─────────────────────────────────────────
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/mark-read/', views.notifications_mark_read, name='notifications_mark_read'),
    path('notifications/sse/', views.notifications_sse, name='notifications_sse'),
]
