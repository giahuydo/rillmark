# 2. How SCIO works today (from using it)

← [Overview](README.md) · [3. Scope](03-scope.md) →

We used a Pro Plus trial with an Owner account, two disposable Teams, and a second identity invited into Team B. We switched that identity between **User, Read Only, Admin and a custom role**, so most rows below were checked from both sides. We used generated test images and one browser player. Where a row says *API response*, we read the reply of SCIO's own web app call in the browser; we never sent hand-made requests.

### Teams and people

| Area | What we saw | Label |
|---|---|---|
| Teams | Separate workspaces with their own Screens, members and Screen limit. A Team limit edited 0 → 1 persisted, bounded by account licences; the plan page reads "0 screens used by Default team + 1 screens reserved for other teams" | DOCUMENTED + VERIFIED UI |
| Team context | The Owner works in one active Team at a time (switched Default → Team B by hand). A folder created "for Team A" from Default context is still Default-owned: an easy mistake we made ourselves | VERIFIED UI |
| Members | Add (admin sets a password, forced change at first sign-in) ≠ Invite (email). The invited identity accepted and appeared as User in Team B. Per-member actions: **Reset password, Change Role, Remove From Team, Delete User**; per-Team menu: Update Team, Remove Team | VERIFIED UI |
| Roles | **Super Admin is offered only in the Default Team**; other Teams offer Admin, User and Read Only. Content Proposal/Approval are listed but disabled (out of scope anyway). Owner is fixed | VERIFIED UI |
| Team Admin role | Sees and manages **only its own Team** in Account Members: Add, Invite, change role, remove from Team, Update Team; can grant Admin, User, Read Only or a custom role, **not Super Admin**; no Delete User, Reset password, Remove Team or Add Team. Can change folder permissions, but only *Everyone on this team* or *Admin Only*: **Everyone in the account is disabled and other Teams are not offered**. Can Remove a Screen and Move To OnHold, but **Move To Team is absent**. No billing or company settings | VERIFIED UI (Team Admin) |
| Read Only role | Even with the Screen's folder at **Edit**: no Edit button, Move/Remove disabled, folder shows only View Permission, **Push To Screens removed** from the Asset menu, Templates and OptiDev gone from the top nav; Preview and Download icons remain; shared folders stay visible. The role caps what a folder grant allows | VERIFIED UI (Read Only) |
| Custom roles | Managed from **Manage Roles on the Default Team**, but usable in every Team (account-wide). Tags can be enabled only after Edit. A grid of Screens, Files/Assets, Playlists, Schedules × Create / Edit / Delete / Tags. **No View, Download, Assign or Members toggle**: visibility comes from folders | VERIFIED UI |
| Custom role in practice | A role with **only Screens Edit**: Add Screen and New Folder hidden; Remove disabled; Tags field disabled; Upload/Create hidden on Files/Assets even in the User's own folder. It can still assign content: Edit Screen → pick an Asset → Save, and Push, both succeed when the Screen's folder is Edit. **Assigning needs no Files capability**, only View on the source | VERIFIED UI + API response (normal User) |

### Folders and sharing

| Area | What we saw | Label |
|---|---|---|
| Folder sharing | Per-tab folders; one Edit/View level per folder. Subjects offered: **Everyone on this team · Everyone in the account · Admin Only**, plus individual Teams (the picker says "users and teams", but a user who belongs only to another Team was not offered). Adding another Team **shares without moving ownership** (owning Team shown as a locked row). Folder menu: Move To, Pin, Rename, Replace Thumbnail, Edit Tags/Description, Change Permission, Get Info, Share Link, Move to Trash | DOCUMENTED + VERIFIED UI |
| "Admin Only" vs a Team grant | A Default-Team folder set to *Admin Only* **plus** a Team B grant is visible to a non-admin Team B member. Admin Only limits the owning Team's members; an explicit Team grant covers all members of that Team | VERIFIED UI |
| Inheritance | A child copies its parent's permissions at creation (the New Folder dialog is pre-filled with them); a later change on the parent (View → Edit) left the child at View, and no apply-to-subfolders control was offered | DOCUMENTED + VERIFIED UI |
| Folders created by a User | A normal User can create Screen and Asset folders at the Team root and upload into them. The new folder gets *owning Team + Everyone on this team, Edit*; the User can rename, move and remove it, but sees only **View Permission**, so **only admins share folders** | VERIFIED UI (normal User) |

### Assets

| Area | What we saw | Label |
|---|---|---|
| Asset actions | Live/Expire, Push To Screens, Add to Playlists, Show Playlists Using This, Duplicate, Replace, Move, Rename, Tags, Copy URL/ID, Download, Move to Trash. Detail view: name, processing status, type, size, dimensions, path, tags | VERIFIED UI |
| Upload | "Create And Share" warning lists recipients before uploading into a shared folder; processing is asynchronous; accepted types include Office, video, images, audio, HLS/DASH | VERIFIED UI |

### Screens

| Area | What we saw | Label |
|---|---|---|
| Pairing | Browser player shows a code; pairing places the Screen in the current Team | VERIFIED UI |
| Screen settings | Edit Screen: device name, tags, **content type Asset / Playlist / Schedule / Stop Playing**, selected content, scale, orientation; Operational Schedule; Advanced (functional location, location, background, content tag rule, Sync Play, downloading status, offline indicator, mute, more). Footer: Preview, Schedule, Save, Identify Screen, Refresh & Relaunch. Row menu: View Device Info, Troubleshoot with OptiBot, Identify, Move, Pin, Move To OnHold Devices, Move To Team, Remove | VERIFIED UI |
| OnHold | A confirm dialog warns the screen will show blank content. The Screen moves to a system **OnHold Devices** folder, shows "No content assigned", and the Team counter drops (1/1 → 0/1). Reactivation is a plain **Move** out of that folder: the earlier assignment comes back and the counter returns to 1/1. A Team Admin can do this | VERIFIED UI (Team Admin) |
| Move To Team | Owner-only (absent for a Team Admin). The dialog lists the other Teams. Into a full Team, SCIO offers **"Move License"** (move one licence with the Screen) rather than the hard error the Help Center describes; into a Team with a free licence it just moves. The Screen lands in the destination Team's **Home** folder and its **assignment is cleared** ("No content assigned"), even when the content was visible to the destination Team. The source Team keeps its Screen limit; only usage drops | VERIFIED UI |

### Assigning content

| Area | What we saw | Label |
|---|---|---|
| Cross-Team assignment | A normal Team B User picked an Asset from a Default-owned folder shared to Team B at **View**, assigned it via **Edit Screen**, and the player rendered it. **Push to Screen** by the same User was accepted and logged as `Screens: edited` | VERIFIED UI (normal User) + Audit Log |
| Screen-folder View | With the Screen's folder at View, the User's write controls (Edit, Move, Remove, Add Screen, New Folder, folder Rename/Move/Edit Screens) were hidden or disabled; the folder offers only **View Permission** (read-only). **But Push to Screen still lists that Screen as a target and lets the User press Push; the server then refuses**: the `PushToScreens` mutation returns `PERMISSION_DENIED / FORBIDDEN` and the dialog shows "Permission denied". The same refusal happens when the Asset comes from the User's own Edit folder, so the deciding grant is the **Screen's** folder. SCIO enforces rule S1 on the server, and its UI is not fully consistent | VERIFIED UI + VERIFIED API response (normal User) |
| Revoking a share | Removing Team B from the source folder **keeps the existing assignment**: the Screen still lists it, as "Asset: (Not available)" for the Team B User, the Edit Screen picker shows it empty, and the folder disappears from that User's pickers | VERIFIED UI (normal User) |
| Playlist with an item the user can't see | A User with View on a Playlist folder can assign a playlist whose items include an Asset from a folder they cannot see (`UpdateDevice` succeeded). Opening the playlist shows **every item's name and thumbnail**, and clicking the hidden item opens its full detail (preview, metadata, folder path, Download and Move to Trash buttons; not clicked) | VERIFIED UI (normal User); server effect of those buttons UNKNOWN |

### Audit

| Area | What we saw | Label |
|---|---|---|
| Audit Log | Folder, permission, role-creation, upload, Screen-edit and login events with Team and actor; Push and Edit both appear as "Edited". **Not shown:** denied actions (two refused Pushes) and a member's role change | VERIFIED UI |

**Still UNKNOWN in SCIO** (the plan picks a rule in [§5](05-data-model-and-authorization.md); full list in [§11](10-risks-and-open-questions.md#11-open-questions-dont-block-the-start)): Replace or Delete of an Asset that is assigned; whether a Super Admin's view spans Teams; storage and upload-size limits per plan (not shown anywhere we looked in the UI).

**What we copy from SCIO's UX:** the Create And Share warning, the Move License offer, shared folders surfacing inside the Edit Screen picker, immediate `Asset: <name>` feedback in the Screens list, and the small role grid.

**Where we deliberately differ:** pickers (including Push) show only Screens the user may change, instead of failing after Submit; denied actions and member role changes are written to the audit log; inside a playlist, an item the viewer cannot see is shown as a placeholder ("Non-accessible item"), with no name, thumbnail, metadata or file actions.

---

← [Overview](README.md) · [3. Scope](03-scope.md) →
