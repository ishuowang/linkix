import QRCode from "qrcode";
import { fileURLToPath } from "node:url";

await QRCode.toFile(
  fileURLToPath(new URL("../public/assets/telegram-bot-qr.png", import.meta.url)),
  "https://t.me/vid_dld_bot",
  {
    width: 512,
    margin: 2,
    errorCorrectionLevel: "M",
    color: {
      dark: "#1d1a15",
      light: "#ffffff",
    },
  },
);

console.log("generated public/assets/telegram-bot-qr.png");
