import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { tools } from "./tools.js";

const API_BASE = process.env.GRAPHRAG_API || "http://localhost:8080";

const server = new Server(
  { name: "graphrag", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  const endpoints: Record<string, string> = {
    ask_codebase: `/query?q=${encodeURIComponent(args?.query as string)}`,
    get_node_context: `/node/${encodeURIComponent(args?.name as string)}`,
    get_community_summary: `/community/${encodeURIComponent(args?.community_name as string)}`,
    find_owner: `/owner?q=${encodeURIComponent(args?.query as string)}`,
    list_open_tasks: `/tasks${args?.filter ? `?filter=${encodeURIComponent(args.filter as string)}` : ""}`,
  };

  const url = `${API_BASE}${endpoints[name]}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    return {
      content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
    };
  } catch (error) {
    return {
      content: [{ type: "text", text: `Error calling ${name}: ${error}` }],
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
