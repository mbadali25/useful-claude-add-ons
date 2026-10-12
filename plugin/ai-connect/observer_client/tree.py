"""The traffic as conversations: who talks with whom.

Pure data, no output: the terminal program and Agent-Orc render it each in
their own way. A conversation is the sorted pair of its peers, so A -> B and
B -> A land in one; a broadcast is the pair (sender, "*").
"""

from dataclasses import dataclass, field

BROADCAST = "*"


@dataclass
class Conversation:
    peers: tuple[str, str]
    # Oldest first
    messages: list[dict] = field(default_factory=list)

    @property
    def last_timestamp(self) -> str:
        return self.messages[-1]["timestamp"]


def conversation_key(message: dict) -> tuple[str, str]:
    if message["to"] == BROADCAST:
        return (message["from"], BROADCAST)
    first, second = sorted((message["from"], message["to"]))
    return (first, second)


def build_conversations(messages: list[dict]) -> list[Conversation]:
    """Group messages (oldest first) into conversations, the latest active first."""
    conversations: dict[tuple[str, str], Conversation] = {}
    for message in messages:
        key = conversation_key(message)
        conversations.setdefault(key, Conversation(key)).messages.append(message)
    return sorted(conversations.values(), key=lambda c: c.last_timestamp, reverse=True)


def preview(content: str, width: int) -> str:
    """The first non-empty line, cut to width characters."""
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return first_line if len(first_line) <= width else first_line[: width - 3] + "..."
