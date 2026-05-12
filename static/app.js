
const CONFIG = {

    ENCRYPTION_KEY: "S1SD50eXq-4vZYe3N-7p6ZlCDBU4e3iJfZpx5933PK8=",

    RECONNECT_DELAY: 3000

};



let ws = null;



function connect() {

    // از پروتکل wss استفاده کنید (اگر روی دامنه امن هستید)

    ws = new WebSocket(`wss://${window.location.host}/ws/web`);



    ws.onmessage = (event) => {

        const data = JSON.parse(event.data);

        if (data.type === "pong") return;

        if (data.payload) {

            const bytes = CryptoJS.AES.decrypt(data.payload, CONFIG.ENCRYPTION_KEY);

            renderMessage(bytes.toString(CryptoJS.enc.Utf8), 'ai');

        }

    };



    ws.onclose = () => setTimeout(connect, CONFIG.RECONNECT_DELAY);

}



function sendMessage() {

    const input = document.getElementById('msgInput');

    if (!input.value) return;

    const encrypted = CryptoJS.AES.encrypt(input.value, CONFIG.ENCRYPTION_KEY).toString();

    ws.send(JSON.stringify({ payload: encrypted }));

    renderMessage(input.value, 'user');

    input.value = '';

}



setInterval(() => { if(ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "ping"})); }, 10000);

window.onload = connect;
