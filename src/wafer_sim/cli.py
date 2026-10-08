import argparse
import sys


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if '--config' in argv and (not argv or argv[0].startswith('-')):
        print('Legacy GOAL entry; use wafer-sim goal-replay explicitly.',file=sys.stderr)
        argv.insert(0,'goal-replay')
    parser=argparse.ArgumentParser(description='WoW simulation abstractions and design-gain prediction')
    commands=parser.add_subparsers(dest='command')
    current=commands.add_parser('boundary-design',help='Current frozen 24-cell study on eex005')
    current.add_argument('--output',required=True);current.add_argument('--tests',required=True)
    current.add_argument('--cpus',help='Two allowed CPU IDs, comma separated')
    analysis=commands.add_parser('analyze-boundary-design',help='Audit and compare completed study')
    analysis.add_argument('--run',required=True);analysis.add_argument('--output',required=True)
    legacy=commands.add_parser('goal-replay',help='Historical full GOAL campaign (separate input contract)')
    for field in ('config','upstream','binary','output'):legacy.add_argument('--'+field,required=True)
    args=parser.parse_args(argv)
    if args.command=='boundary-design':
        from wafer_sim.experiments.boundary_design import run
        run(args.output,args.tests,[int(x) for x in args.cpus.split(',')] if args.cpus else None)
    elif args.command=='analyze-boundary-design':
        from wafer_sim.experiments.boundary_design import analyze_run
        analyze_run(args.run,args.output)
    elif args.command=='goal-replay':
        from wafer_sim.experiments.runner import run_campaign
        run_campaign(args.config,args.upstream,args.binary,args.output)
    else:parser.print_help()


if __name__ == "__main__":
    main()
