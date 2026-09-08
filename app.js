
const STORAGE_KEY = "yuraChaldeaStateV001";


// ===== Latest FGO Pickup =====
// 公式発表をもとに更新。次回以降はこのオブジェクトを書き換えるだけでPU欄を更新できます。
const latestPickup = {
  updatedAt: "2026-09-08 15:20",
  title: "3500万DL記念ピックアップ召喚",
  start: "2026-09-02T18:00:00+09:00",
  end: "2026-09-16T12:59:00+09:00",
  periodText: "2026/9/2 18:00 ～ 9/16 12:59",
  servants: [
    "★5 アルトリア･キャスター〔バーサーカー〕",
    "パッションリップ〔セイバー〕",
    "ラーヴァ／ティアマト〔アーチャー〕",
    "メリュジーヌ〔ルーラー〕",
    "BB",
    "玉兎",
    "ほか全12騎・6種類の召喚"
  ],
  officialUrl: "https://news.fate-go.jp/2026/09/3500man_pu/"
};

function renderPickup() {
  const now = new Date();
  const start = new Date(latestPickup.start);
  const end = new Date(latestPickup.end);

  $("pickupTitle").textContent = latestPickup.title;
  $("pickupPeriod").textContent = latestPickup.periodText;
  $("pickupUpdated").textContent = `情報更新：${latestPickup.updatedAt}`;
  $("pickupOfficialLink").href = latestPickup.officialUrl;

  $("pickupServants").innerHTML = latestPickup.servants
    .map(name => `<span class="servant-chip">${escapeHtml(name)}</span>`)
    .join("");

  const status = $("pickupStatus");
  const countdown = $("pickupCountdown");

  status.classList.remove("ended", "upcoming");

  if (now < start) {
    status.textContent = "開催予定";
    status.classList.add("upcoming");
    const hours = Math.ceil((start - now) / 3600000);
    countdown.textContent = `開始まで約${hours}時間`;
  } else if (now <= end) {
    status.textContent = "開催中";
    const diffMs = end - now;
    const days = Math.floor(diffMs / 86400000);
    const hours = Math.ceil((diffMs % 86400000) / 3600000);
    countdown.textContent = days > 0
      ? `終了まで約${days}日${hours}時間`
      : `終了まで約${hours}時間`;
  } else {
    status.textContent = "終了";
    status.classList.add("ended");
    countdown.textContent = "このピックアップは終了しました";
  }
}


const defaultState = {
  stone: 0,
  ticket: 0,
  fragment: 0,
  targetPulls: 330,
  history: []
};

let state = loadState();

const $ = (id) => document.getElementById(id);

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return { ...defaultState, ...(saved || {}) };
  } catch {
    return { ...defaultState };
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  render();
}

function fragmentStoneEquivalent() {
  return Math.floor(state.fragment / 7);
}

function totalPulls() {
  return Math.floor(state.stone / 3) + state.ticket + fragmentStoneEquivalent();
}

function resourceLabel(type) {
  return {
    stone: "聖晶石",
    ticket: "呼符",
    fragment: "聖晶片"
  }[type];
}

function unitLabel(type) {
  return type === "ticket" ? "枚" : "個";
}

function formatDate(iso) {
  return new Intl.DateTimeFormat("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(iso));
}

function yuraLine(pulls, remaining) {
  if (pulls <= 0) return "ユラ「まずは現在地を登録するのじゃ。」";
  if (remaining <= 0) return "ユラ「天井分確保……！これで推しが来ても戦えるぞい。」";
  const ratio = pulls / state.targetPulls;
  if (ratio >= 0.75) return "ユラ「かなり貯まってきたぞ。ここからの寄り道が一番危険じゃ。」";
  if (ratio >= 0.5) return "ユラ「折り返し突破じゃ。石を守るのじゃぞ、りゅう。」";
  if (ratio >= 0.25) return "ユラ「いい調子じゃ。単発の誘惑には気をつけるんじゃぞ。」";
  return "ユラ「まだ序盤じゃな。焦らず貯蔵していこうぞ。」";
}

function render() {
  const pulls = totalPulls();
  const remaining = Math.max(0, state.targetPulls - pulls);
  const progress = Math.min(100, (pulls / state.targetPulls) * 100);

  $("stoneValue").textContent = state.stone.toLocaleString();
  $("ticketValue").textContent = state.ticket.toLocaleString();
  $("fragmentValue").textContent = state.fragment.toLocaleString();
  $("totalPulls").textContent = pulls.toLocaleString();
  $("remainingPulls").textContent = remaining.toLocaleString();
  $("targetPullsInput").value = state.targetPulls;
  $("progressBar").style.width = `${progress}%`;
  $("progressText").textContent = `${pulls.toLocaleString()} / ${state.targetPulls.toLocaleString()}連`;
  $("yuraComment").textContent = yuraLine(pulls, remaining);

  const list = $("historyList");
  if (!state.history.length) {
    list.innerHTML = '<p class="empty">まだ記録はありません。</p>';
    return;
  }

  list.innerHTML = state.history
    .slice()
    .reverse()
    .map(item => {
      const sign = item.operation === "add" ? "+" : "−";
      const cls = item.operation === "add" ? "plus" : "minus";
      const memo = item.memo ? `・${escapeHtml(item.memo)}` : "";
      return `
        <div class="history-item">
          <div class="history-main">${resourceLabel(item.type)}${memo}</div>
          <div class="history-meta">${formatDate(item.date)}</div>
          <div class="history-amount ${cls}">${sign}${item.amount}${unitLabel(item.type)}</div>
        </div>
      `;
    })
    .join("");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("saveBtn").addEventListener("click", () => {
  const type = $("resourceType").value;
  const operation = $("operationType").value;
  const amount = Number($("amountInput").value);
  const memo = $("memoInput").value.trim();

  if (!Number.isFinite(amount) || amount <= 0) {
    alert("数量を1以上で入力しての。");
    return;
  }

  const delta = operation === "add" ? amount : -amount;
  const next = state[type] + delta;

  if (next < 0) {
    alert(`${resourceLabel(type)}がマイナスになってしまうぞい。`);
    return;
  }

  state[type] = next;
  state.history.push({
    type,
    operation,
    amount,
    memo,
    date: new Date().toISOString()
  });

  $("amountInput").value = "";
  $("memoInput").value = "";
  saveState();
});

$("saveTargetBtn").addEventListener("click", () => {
  const value = Number($("targetPullsInput").value);
  if (!Number.isFinite(value) || value <= 0) {
    alert("目標連数を正しく入力しての。");
    return;
  }
  state.targetPulls = Math.floor(value);
  saveState();
});

$("clearHistoryBtn").addEventListener("click", () => {
  if (!confirm("履歴だけ削除するぞい？ 残高はそのままです。")) return;
  state.history = [];
  saveState();
});

$("resetBtn").addEventListener("click", () => {
  if (!confirm("残高・目標・履歴をすべて初期化するぞい？")) return;
  state = { ...defaultState, history: [] };
  saveState();
});

function localYuraReply(message) {
  const pulls = totalPulls();
  const remaining = Math.max(0, state.targetPulls - pulls);
  const normalized = message.toLowerCase();

  if (message.includes("何個") || message.includes("残高") || message.includes("今")) {
    return `今は聖晶石${state.stone}個、呼符${state.ticket}枚、聖晶片${state.fragment}個。合計で約${pulls}連分じゃ。`;
  }

  if (message.includes("天井") || message.includes("あと")) {
    return remaining === 0
      ? "天井分はもう確保できておるぞい。よく耐えたのう。"
      : `目標${state.targetPulls}連まで、あと${remaining}連分じゃ。`;
  }

  if (message.includes("引いて") || message.includes("ガチャ") || message.includes("回して")) {
    if (pulls >= state.targetPulls) {
      return `天井分${state.targetPulls}連は確保済みじゃ。ただしマリー・オルタ用を崩すなら、ユラは一応止めるぞい。`;
    }
    if (pulls >= state.targetPulls * 0.75) {
      return `かなり貯まっておる。じゃが目標まであと${remaining}連。ここで崩すのはちょっと怖いのう……。`;
    }
    return `今は${pulls}連分、目標まであと${remaining}連じゃ。マリー・オルタ優先なら今回は我慢寄りじゃな。`;
  }

  if (message.includes("褒め") || message.includes("えら")) {
    return `えらいぞ、りゅう。現在${pulls}連分じゃ。ちゃんと貯蔵できておる。`;
  }

  return `現在は${pulls}連分。目標まであと${remaining}連じゃ。Ver.0.01なので、今は残高ベースの簡易相談だけできるぞい。`;
}

$("chatSendBtn").addEventListener("click", sendChat);
$("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendChat();
});

function sendChat() {
  const input = $("chatInput");
  const message = input.value.trim();
  if (!message) return;

  const chat = $("chatBox");
  chat.insertAdjacentHTML("beforeend", `<div class="bubble user">${escapeHtml(message)}</div>`);
  const reply = localYuraReply(message);
  chat.insertAdjacentHTML("beforeend", `<div class="bubble yura">${escapeHtml(reply)}</div>`);
  input.value = "";
  chat.scrollTop = chat.scrollHeight;
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}

render();
renderPickup();

setInterval(renderPickup, 60 * 1000);
