"""Local STDIO tools. Model inference/sign-in are exclusively host-owned."""
import argparse
import base64
import json
from pathlib import Path
from typing import Literal
from jsonschema import Draft202012Validator
from mcp.server import MCPServer
from mcp.types import CallToolResult,TextContent,ImageContent,ToolAnnotations
from .contracts import HarnessError
from .mcp_service import MCPService

INSTRUCTIONS=(
    'PCB Harness: local scratch-board tools, no model API key. Start with pcb_status and '
    'pcb_connect; query current revision before each write and use a unique action_id. '
    'Caller chooses every position/path/layer/via; no autorouter. Strict mode rejects '
    'new geometric violations; connectivity and release readiness are separate. Never '
    'retry uncertain writes or reset recovery. Memory is test-only. Native writes require '
    'the verified connected KiCad 10.0.6 scratch backend. Frozen run_budget counts every admitted write '
    'including invalid/replayed requests; reconnect never renews limits. After expiry use queries '
    'for inspection. Inference belongs to the host.')


def response(data):
    metadata={k:v for k,v in data.items() if k!='_image_bytes'}
    content=[TextContent(type='text',text=json.dumps(metadata,allow_nan=False))]
    if metadata.get('ok',True) and data.get('_image_bytes') is not None:
        content.append(ImageContent(type='image',data=base64.b64encode(data['_image_bytes']).decode(),mime_type='image/png'))
    return CallToolResult(content=content,structured_content=metadata,is_error=not metadata.get('ok',True))


class StrictMCPServer(MCPServer):
    """Reject undeclared top-level arguments instead of SDK coercion/ignoring."""
    async def list_tools(self):
        tools=await super().list_tools()
        for tool in tools:
            tool.input_schema={**tool.input_schema,'additionalProperties':False}
        return tools

    async def call_tool(self,name,arguments,context=None):
        tool=next((t for t in await self.list_tools() if t.name==name),None)
        if tool is not None:
            error=next(Draft202012Validator(tool.input_schema).iter_errors(arguments),None)
            if error is not None:
                operation={'pcb_execute':'execute','pcb_create_checkpoint':'create_checkpoint',
                    'pcb_restore_checkpoint':'restore_checkpoint'}.get(name)
                if operation is not None:return response(self.service.reject_write(operation,error.message))
                return response({'ok':False,'error_code':'INVALID_ARGUMENT','message':error.message})
        return await super().call_tool(name,arguments,context)


def create_server(service):
    async def raw_write_boundary(context,call_next):
        params=context.params
        if context.method=='tools/call' and isinstance(params,dict):
            operation={'pcb_execute':'execute','pcb_create_checkpoint':'create_checkpoint',
                'pcb_restore_checkpoint':'restore_checkpoint'}.get(params.get('name'))
            arguments=params.get('arguments')
            if operation and arguments is not None and not isinstance(arguments,dict):
                service.reject_write(operation,'MCP arguments must be an object')
                # Retain SDK INVALID_PARAMS wire error; the identifiable write is accounted.
        return await call_next(context)

    server=StrictMCPServer('PCB Harness',version='0.0.1',instructions=INSTRUCTIONS,
        log_level='WARNING',middleware=[raw_write_boundary])
    server.service=service
    read=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)
    write=ToolAnnotations(read_only_hint=False,destructive_hint=True,idempotent_hint=False,open_world_hint=False)
    verification=read if service.backend=='memory' else ToolAnnotations(
        read_only_hint=False,destructive_hint=False,idempotent_hint=False,open_world_hint=False)

    @server.tool(annotations=read,structured_output=False)
    def pcb_status() -> CallToolResult:
        """Report connection/configured backend. Memory is test-only; no inference keys needed."""
        return response(service.status())

    @server.tool(annotations=write,structured_output=False)
    def pcb_connect() -> CallToolResult:
        """Connect the fixed launch-configured backend/run. Never falls back from KiCad to Memory."""
        return response(service.connect())

    @server.tool(annotations=read,structured_output=False)
    def pcb_summary() -> CallToolResult:
        """Read board counts and current revision. Native checks unknown until verified."""
        return response(service.call('summary'))

    @server.tool(annotations=read,structured_output=False)
    def pcb_get_footprint(ref: str) -> CallToolResult:
        """Read exact footprint/pad geometry, lock/side and revision. Coordinates are mm."""
        return response(service.call('get_footprint',ref=ref))

    @server.tool(annotations=read,structured_output=False)
    def pcb_net_info(net: str) -> CallToolResult:
        """Read canonical net's pads, explicit copper and length in mm; does not plan routes."""
        return response(service.call('net_info',net=net))

    @server.tool(annotations=verification,structured_output=False)
    def pcb_list_unrouted() -> CallToolResult:
        """Read current unconnected findings and revision; never implies release readiness."""
        return response(service.call('list_unrouted'))

    @server.tool(annotations=write,structured_output=False)
    def pcb_execute(action: Literal['place_footprint','move_footprint','rotate_footprint','flip_footprint',
                    'route_track','add_via','delete_track','add_zone','fill_zones'],
                    args: dict,expected_revision: str,action_id: str,
                    mode: Literal['strict','permissive']='strict') -> CallToolResult:
        """Apply caller's explicit intent with revision/locks/ID checks. Native edits require the verified 10.0.6 scratch backend.

        Query backend capabilities first. route_track needs net, layer, points_mm and width_mm;
        move_footprint needs ref, dx_mm, dy_mm; place needs ref, x_mm, y_mm plus optional side/rotation_deg;
        through via needs net, x_mm, y_mm, drill_mm, dia_mm, layers=[F.Cu,B.Cu].
        Strict rolls back new geometric violations; permissive commits with reported deltas.
        """
        return response(service.call('execute',name=action,args=args,expected_revision=expected_revision,
            action_id=action_id,mode=mode))

    @server.tool(annotations=write,structured_output=False)
    def pcb_create_checkpoint(name: str,expected_revision: str) -> CallToolResult:
        """Save named baseline only with fresh revision. Failure can require recovery; not a release."""
        return response(service.call('create_checkpoint',name=name,expected_revision=expected_revision))

    @server.tool(annotations=write,structured_output=False)
    def pcb_restore_checkpoint(name: str,expected_revision: str) -> CallToolResult:
        """Restore a named baseline with current revision; external/uncertain edits block restore."""
        return response(service.call('restore_checkpoint',name=name,expected_revision=expected_revision))

    @server.tool(annotations=verification,structured_output=False)
    def pcb_verify_geometry() -> CallToolResult:
        """Read geometry/connectivity findings and revision. Native DRC/parity or Memory test model;
        does not run ERC or grant fabrication release. Native verification copies saved artifacts.
        """
        return response(service.call('verify'))

    @server.tool(annotations=write,structured_output=False)
    def pcb_disconnect() -> CallToolResult:
        """Release board connection while retaining fixed run journal/recovery state. Does not reset."""
        return response(service.disconnect())

    visual=ToolAnnotations(read_only_hint=False,destructive_hint=False,idempotent_hint=False,open_world_hint=False)

    @server.tool(annotations=visual,structured_output=False)
    def pcb_render_board(layers: list[str]=['F.Cu','B.Cu'],width_px: int=1024) -> CallToolResult:
        """Return PNG + layer/revision/mm mapping for whole board. Edge.Cuts always included.
        Memory output is labelled test-only; native uses a stable saved copy, not screen capture.
        """
        return response(service.render(layers,width_px=width_px))

    @server.tool(annotations=visual,structured_output=False)
    def pcb_render_region(region_mm: list[float],layers: list[str]=['F.Cu','B.Cu'],width_px: int=1024) -> CallToolResult:
        """Return PNG crop [xmin,ymin,xmax,ymax] in board mm with exact mapping/revision.
        Crop must lie inside the outline; image is supplementary to structured geometry.
        """
        return response(service.render(layers,region_mm=region_mm,width_px=width_px))

    @server.tool(annotations=visual,structured_output=False)
    def pcb_capture_editor() -> CallToolResult:
        """Capture only bound PCB Editor window on macOS with existing Screen Recording permission.
        Requires explicit api-<PID>.sock; no desktop/render fallback, no board pixel calibration.
        """
        return response(service.capture_editor())

    return server


def main():
    parser=argparse.ArgumentParser(description='PCB Harness local MCP; inference stays in your subscribed host.')
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--run-directory',type=Path,required=True)
    parser.add_argument('--backend',choices=['kicad','memory'],default='kicad')
    parser.add_argument('--project',type=Path)
    parser.add_argument('--max-actions',type=int,default=300)
    parser.add_argument('--max-duration-seconds',type=float,default=1200)
    parser.add_argument('--socket',default='ipc:///tmp/kicad/api.sock')
    args=parser.parse_args()
    try:service=MCPService(workspace=args.workspace,run_directory=args.run_directory,
        backend=args.backend,project=args.project,socket=args.socket,
        max_actions=args.max_actions,max_duration_seconds=args.max_duration_seconds)
    except (HarnessError,OSError) as error:parser.exit(2,f'PCB Harness startup error: {error}\n')
    try:create_server(service).run(transport='stdio')
    finally:service.close()


if __name__=='__main__':main()
