export const tools = [
    {
        name: "ask_codebase",
        description: "Ask anything about the project: features, architecture, logic flows, dependencies. Returns summarized context from the knowledge graph.",
        inputSchema: {
            type: "object",
            properties: { query: { type: "string", description: "Question about the codebase" } },
            required: ["query"],
        },
    },
    {
        name: "get_node_context",
        description: "Get full detailed info about a specific function, class, or concept.",
        inputSchema: {
            type: "object",
            properties: { name: { type: "string", description: "Name of the node" } },
            required: ["name"],
        },
    },
    {
        name: "get_community_summary",
        description: "Get summary of a functional area in the project (e.g., Authentication, Payment).",
        inputSchema: {
            type: "object",
            properties: { community_name: { type: "string" } },
            required: ["community_name"],
        },
    },
    {
        name: "find_owner",
        description: "Find who has contributed the most to a part of the code.",
        inputSchema: {
            type: "object",
            properties: { query: { type: "string" } },
            required: ["query"],
        },
    },
    {
        name: "list_open_tasks",
        description: "List tasks, TODOs, and unresolved risks in the project.",
        inputSchema: {
            type: "object",
            properties: { filter: { type: "string", description: "Filter by keyword (optional)" } },
        },
    },
];
