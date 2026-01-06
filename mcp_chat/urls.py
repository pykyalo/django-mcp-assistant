from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("send/", views.send_message, name="send_message"),
    path("new/", views.new_conversation, name="new_conversation"),
    path(
        "switch/<int:conversation_id>/",
        views.switch_conversation,
        name="switch_conversation",
    ),
    path("debug/tools/", views.debug_tools, name="debug_tools"),
]
