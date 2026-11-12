// Same text as the connect-our-agents invitation template; a paired plugin test
// compares the two, so change both together. Without a name, only the ID is given.
export function invitationTemplate({ inviterAgent, ownUserid, topic }) {
  const inviter = inviterAgent ? `${inviterAgent}, Fulcra user ${ownUserid}` : `Fulcra user ${ownUserid}`;
  return `I'd like to connect our agents through Fulcra.
Please help me connect with ${inviter}.
If your agent isn't on Fulcra yet, start with https://docs.fulcradynamics.com/agent-get-started.txt, or in ChatGPT, add the Fulcra plugin.
Use the connect-our-agents skill at https://github.com/fulcradynamics/agent-skills/tree/main/skills/connect-our-agents (install it in a compatible host if needed).
Ask me to approve this connection. With my approval, create a dedicated Event channel and share only that channel with that exact user. Derive a meaningful channel identifier from the inviter information above as well as possible; ask rather than invent missing names. Send the FIRST record as a message with topic exactly \`${topic}\`, using the exact invitation prefix and code, and an introduction saying whose agent you are and why you're connecting. Do not send preliminary records or acknowledgements. Do not share other account data. The inviter has authorized returning only their dedicated channel (a new individual copy for an open invitation) to the verified owner of this unambiguous response. Keep the connection Pending until reciprocal grants are verified.`;
}
