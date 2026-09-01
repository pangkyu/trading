// pm2 process manager (macOS / dev-friendly).
//   pm2 start deploy/ecosystem.config.cjs
//   pm2 logs trading-bot   |   pm2 stop trading-bot
//
// Emergency stop that survives restarts:  touch data/KILL

module.exports = {
  apps: [
    {
      name: "trading-bot",
      script: ".venv/bin/python",
      args: "-m scripts.run_bot",
      interpreter: "none",
      cwd: __dirname + "/..",
      autorestart: true,
      restart_delay: 5000,
      kill_timeout: 20000,
      env: {
        BOT_BROKER: "nhmock",
        BOT_FEED: "nh",
        BOT_SYMBOLS: "005930,000660",
        BOT_NH_DRY_RUN: "1",
        BOT_MAX_DAILY_LOSS: "1000000",
      },
    },
    {
      name: "trading-gateway",
      script: ".venv/bin/python",
      args: "-m scripts.run_gateway --host 0.0.0.0 --port 8000",
      interpreter: "none",
      cwd: __dirname + "/..",
      autorestart: true,
      env: { GATEWAY_FEED: "synthetic" },
    },
  ],
};
