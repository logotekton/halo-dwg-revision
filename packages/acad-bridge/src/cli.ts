import { runDwg2Dxf } from "./commands/dwg2dxf";
import { runDxf2Dwg } from "./commands/dxf2dwg";
import { runInfo } from "./commands/info";
import { runStats } from "./commands/stats";

const USAGE = `acad-bridge -- @node-projects/acad-ts DWG/DXF bridge (Halo CAD W2-05)

Usage:
  acad-bridge dwg2dxf <in.dwg> <out.dxf> [--version AC1032]
  acad-bridge dxf2dwg <in.dxf> <out.dwg> [--version AC1027]
  acad-bridge stats <in.dwg|in.dxf> --out <json>
  acad-bridge info <in.dwg|in.dxf>
`;

function main(argv: string[]): number {
  const [command, ...rest] = argv;
  switch (command) {
    case "dwg2dxf":
      return runDwg2Dxf(rest);
    case "dxf2dwg":
      return runDxf2Dwg(rest);
    case "stats":
      return runStats(rest);
    case "info":
      return runInfo(rest);
    case "-h":
    case "--help":
      process.stdout.write(USAGE);
      return 0;
    case undefined:
      process.stderr.write(USAGE);
      return 1;
    default:
      process.stderr.write(`Unknown command: ${command}\n\n${USAGE}`);
      return 1;
  }
}

try {
  process.exitCode = main(process.argv.slice(2));
} catch (err) {
  const message = err instanceof Error ? (err.stack ?? err.message) : String(err);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
}
