import argparse


def main():
    parser = argparse.ArgumentParser(description="Matched fixed-state WoW application experiment")
    parser.add_argument("--config", required=True)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from wafer_sim.experiments.runner import run_campaign
    run_campaign(args.config, args.upstream, args.binary, args.output)


if __name__ == "__main__":
    main()
