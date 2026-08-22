def messages_for_plan(event, plan):
    messages = [{"title": "AI plan ready", "message": f"CampusFlow generated a validated operational plan for {event['title']}."}]
    for volunteer in plan.get("volunteers", []):
        messages.append({"title": "Volunteer recommendation", "message": f"{volunteer['name']} is recommended for {event['title']} ({volunteer.get('assignment_type', 'event support')})."})
    return messages
