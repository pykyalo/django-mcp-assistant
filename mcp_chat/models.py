from django.db import models


class Conversation(models.Model):
    """Represents a chat conversation"""

    title = models.CharField(max_length=200, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.created_at.strftime('%Y-%m-%d')})"


class Message(models.Model):
    """Individual messages in a conversation"""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(
        max_length=20
    )  # 'user', 'assistant', 'tool_use', 'tool_result'
    content = models.TextField()
    tool_calls = models.JSONField(null=True, blank=True)  # Store tool call metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
