SECRET TRAITOR — ONLINE HOSTING GUIDE
====================================

This package is prepared for a Render web service. Render will give the game a public HTTPS link so friends in different houses can join.

IMPORTANT LIMITATIONS
- This is still a prototype, not a finished secure online game.
- Rooms and player data are stored in server memory. They are erased if the service restarts or goes idle.
- Render's free service may sleep after 15 minutes without traffic, and the next visit can take about a minute to wake it up.
- Do not use this prototype for private or sensitive information. Anyone who has the public link can visit the site.
- If the host service restarts during a game, the room will be lost.

PUBLISH THE FILES USING GITHUB + RENDER
1. Sign in to GitHub (github.com). Create an account if needed.
2. Create a NEW repository named secret-traitor.
3. If you want the code hidden, choose Private and connect that GitHub account to Render. Do not put passwords, tokens, or private information in the repository.
4. On GitHub, use Add file > Upload files.
5. Upload these items from this folder:
   - server.py
   - requirements.txt
   - render.yaml
   - the entire public folder, including public/index.html
   Do not upload __pycache__.
6. Commit the files to the repository.
7. Open render.com and sign in.
8. Choose New + > Blueprint (if available), connect GitHub, and select the secret-traitor repository. Render will read render.yaml. Choose the Free plan if asked and deploy.
   Alternatively choose New + > Web Service, connect the repository, choose Python 3, set Build Command to `pip install -r requirements.txt`, Start Command to `python server.py`, and choose Free.
9. Wait for deployment to finish. Open the public URL Render gives you, ending in onrender.com.
10. Create a room there and share the website URL and room code with friends.

Keep in mind: this is a public website link, not a secret invite-only URL. The room code only controls joining a room inside this prototype.
