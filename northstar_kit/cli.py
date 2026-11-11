"""Executable interface: plans require no CF context; writes require --apply."""
import argparse
import json
import sys
from pathlib import Path
from .cf import CF, CFError
from .config import ConfigError, ROOT, load_config, target_for
from .lifecycle import Lifecycle, plan
from .state import State


def main(argv=None):
    parser = argparse.ArgumentParser(description='Northstar demo lifecycle (existing dedicated CF org/space)')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('command', choices=['plan', 'preflight', 'deploy', 'validate', 'reset', 'cleanup'])
    parser.add_argument('--phase', type=int, choices=range(1, 5), required=True)
    parser.add_argument('--mode', choices=['cumulative', 'phase-spaces'], default='cumulative')
    parser.add_argument('--apply', action='store_true', help='apply remote mutations; otherwise deploy returns an offline plan')
    parser.add_argument('--delete-data', action='store_true', help='reset/cleanup: delete owned service instances as well as apps')
    parser.add_argument('--json', action='store_true', help='machine-readable JSON output')
    args = parser.parse_args(argv)
    try:
        if args.delete_data and args.command not in ('reset', 'cleanup'):
            parser.error('--delete-data is valid only for reset/cleanup')
        config = load_config(args.config)
        if args.command == 'plan' or (args.command == 'deploy' and not args.apply):
            result = plan(config, args.phase, args.mode)
        else:
            state = State(ROOT / '.state', target_for(config, args.phase, args.mode))
            with state.locked(), CF(timeout=config['timeout_seconds']).isolated() as cf:
                lifecycle = Lifecycle(config, args.phase, args.mode, cf, state)
                if args.command in ('cleanup', 'reset') and not args.apply:
                    result = lifecycle.cleanup_preview(args.delete_data)
                    result['next_action'] = 'redeploy selected phase after removal' if args.command == 'reset' else 'remove previewed resources'
                elif args.command in ('cleanup', 'reset'):
                    result = getattr(lifecycle, args.command)(args.delete_data)
                else:
                    result = getattr(lifecycle, args.command)()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps(result, indent=2))  # Same complete evidence in human-readable indentation.
        if any(c['status'] == 'fail' for c in result.get('checks', [])):
            return 1
        return 0
    except (ConfigError, CFError, OSError, RuntimeError) as error:
        print(json.dumps({'status': 'error', 'detail': str(error)}), file=sys.stderr)
        return 1
