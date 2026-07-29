import { ChatCircleDots } from "@phosphor-icons/react";

export function BotPanel() {
  return (
    <section className="bot-section" aria-labelledby="bot-title">
      <div className="bot-grid">
        <div className="bot-copy">
          <h2 id="bot-title">以后不想打开网页？</h2>
          <p>扫码把机器人加到 Telegram，</p>
          <p>把分享链接直接发给它，自动回传原片。</p>
        </div>

        <div className="bot-cards">
          <div className="bot-card-group is-disabled" aria-label="钉钉机器人待接入">
            <div className="bot-card">
              <ChatCircleDots size={28} weight="light" />
              <strong>钉钉</strong>
              <span>即将接入</span>
            </div>
            <small>钉钉</small>
          </div>

          <a
            className="bot-card-group"
            href="https://t.me/vid_dld_bot"
            target="_blank"
            rel="noreferrer"
            aria-label="打开 Telegram 机器人"
          >
            <div className="bot-card qr-card">
              <img
                src="/assets/telegram-bot-qr.png"
                alt="Telegram 机器人二维码"
                width="88"
                height="88"
              />
            </div>
            <small>Telegram</small>
          </a>
        </div>
      </div>
    </section>
  );
}
