# KIRA Download Bot — Key Shop

## ១. បំពេញតែ BOT_TOKEN ក្នុង .env (ឬ Variables របស់ Hosting)
## ២. Deploy (Dockerfile) រួច /start ក្នុង Bot ហើយចូល 🛠 Admin Panel → ⚙️ ការកំណត់
   - 🔑 NUB API Token → ផ្ញើ Token
   - 👥 Group ID → ផ្ញើ Group ID (ដាក់ Bot ជា Admin ក្នុង Group)
## ៣. Admin Panel → 🤖 ភ្ជាប់ Userbot (លេខទូរស័ព្ទ → កូដ → កូដទីពីរ)

Key: KIRA XXXX XXXX XXXX · /genkey 50 30 5
ដាក់ DB_PATH=/data/data.db លើ Volume ដើម្បីរក្សាទិន្នន័យ។

## ថ្មី៖ ទីតាំងទទួល + កែអត្ថបទមុនផុស
- ផ្ញើតំណ → ជ្រើស Video/MP3 → ជ្រើស **ទីតាំង**: 👤 ផ្ទាល់ខ្លួន · 📢 Channel/Group ដែលបានរក្សាទុក · ➕ បន្ថែមថ្មី
- បន្ថែមថ្មី៖ Bot ត្រូវជា Admin (Post Messages) ហើយអ្នកក៏ត្រូវជា Admin ក្នុងនោះ (ផ្ទៀងផ្ទាត់ម្តងទៀតពេលផុស)
- ទៅ Channel/Group → Bot ផ្ញើ **preview** មកអ្នកមុន: ✏️ កែអត្ថបទ (ប្រើ `{title}` បានសម្រាប់ចំណងជើងដើម) → 📤 ផុសចូល
- ឯកសារធំ (>48MB) ប្រើ Userbot → Group (BIG_GROUP_ID) → Bot យកបន្ត ក៏ចូល preview ដូចគ្នា
- Admin: 📃 បញ្ជី User ទាំងអស់ (ឈ្មោះ · @username · ID, ទំព័រ 15 នាក់, 🚫 = Ban) + 📥 Export CSV
