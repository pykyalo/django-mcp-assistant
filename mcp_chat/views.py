from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from asgiref.sync import sync_to_async


from .models import Conversation, Message
from .mcp_client import MCPClient


# Initialize MCP client (singleton)
mcp_client = MCPClient()


def index(request):
    """Main chat interface"""
    conversations = Conversation.objects.all()[:10]

    # Get or create current conversation
    conversation_id = request.session.get("current_conversation_id")

    if conversation_id:
        try:
            current_conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            current_conversation = Conversation.objects.create(title="New Chat")
            request.session["current_conversation_id"] = current_conversation.id
    else:
        current_conversation = Conversation.objects.create(title="New Chat")
        request.session["current_conversation_id"] = current_conversation.id

    messages = current_conversation.messages.all()

    return render(
        request,
        "mcp_chat/index.html",
        {
            "conversations": conversations,
            "current_conversation": current_conversation,
            "messages": messages,
            "available_tools": mcp_client.get_all_tools(),
        },
    )


@require_http_methods(["POST"])
async def send_message(request):
    """Handle chat message with MCP support (ASYNC!)"""

    user_message = request.POST.get("message", "").strip()

    if not user_message:
        return JsonResponse({"error": "Empty message"}, status=400)

    # Get current conversation (async-safe session access)
    conversation_id = await sync_to_async(
        lambda: request.session.get("current_conversation_id")
    )()

    # Use sync_to_async for database operations
    conversation = await sync_to_async(get_object_or_404)(
        Conversation, id=conversation_id
    )

    # Save user message
    await sync_to_async(Message.objects.create)(
        conversation=conversation, role="user", content=user_message
    )

    # Get conversation history
    messages = await sync_to_async(list)(conversation.messages.all())

    # Build conversation history for MCP client
    history = []
    for msg in messages[:-1]:  # Exclude the message we just added
        if msg.role in ["user", "assistant"]:
            history.append({"role": msg.role, "content": msg.content})

    try:
        # Call MCP client (this is async!)
        result = await mcp_client.send_message(user_message, history)

        assistant_response = result["response"]
        tool_calls = result.get("tool_calls", [])

        # Save assistant message
        await sync_to_async(Message.objects.create)(
            conversation=conversation,
            role="assistant",
            content=assistant_response,
            tool_calls=tool_calls if tool_calls else None,
        )

        # Update conversation title if it's the first exchange
        if await sync_to_async(lambda: conversation.messages.count())() == 2:
            # Generate title from first message
            title = (
                user_message[:50] + "..." if len(user_message) > 50 else user_message
            )
            conversation.title = title
            await sync_to_async(conversation.save)()

        return JsonResponse(
            {
                "user_message": user_message,
                "assistant_response": assistant_response,
                "tool_calls": tool_calls,
            }
        )

    except Exception as e:
        return JsonResponse(
            {"error": f"Error processing message: {str(e)}"}, status=500
        )


def new_conversation(request):
    """Start a new conversation"""
    conversation = Conversation.objects.create(title="New Chat")
    request.session["current_conversation_id"] = conversation.id
    return redirect("index")


def switch_conversation(request, conversation_id):
    """Switch to a different conversation"""
    conversation = get_object_or_404(Conversation, id=conversation_id)
    request.session["current_conversation_id"] = conversation.id
    return redirect("index")


def debug_tools(request):
    """Debug view to see available tools"""
    tools = mcp_client.get_all_tools()
    resources = mcp_client.get_all_resources()

    return render(
        request,
        "mcp_chat/debug.html",
        {
            "tools": tools,
            "resources": resources,
        },
    )
