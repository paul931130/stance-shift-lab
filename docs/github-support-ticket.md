# GitHub Support ticket draft

這份是 ticket 草稿，尚未送出。GitHub 的正式流程是先在獨立 clone 或 worktree 完成敏感資料歷史重寫、確認受影響的 pull request，再 force-push；之後才向 Support 申請清除 cached views、pull-request references 與伺服器上的舊 blob。不要在目前含有未提交修改的工作樹直接做歷史重寫，也不要在 ticket 內貼 API key、`.env.research`、SQLite 或原始新聞資料。

官方流程：[Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

送出前要補齊：

- repository owner / repository name：`paul931130/stance-shift-lab`
- 歷史重寫後的 affected pull request 數量：`[填入]`
- `git-filter-repo` 輸出的 `First Changed Commit(s)`：`[填入]`
- 若有 orphaned LFS objects，附上工具產生的指定檔案；沒有則寫明 `none`

## Subject

Request to remove sensitive historical blob from repository storage

## Body

Hello GitHub Support,

I am the owner of the repository `paul931130/stance-shift-lab`.

I completed a sensitive-data history rewrite in a separate clone/worktree and force-pushed the rewritten repository history. I am requesting removal of the remaining cached views, pull-request references, and the old server-side blob.

Repository: `paul931130/stance-shift-lab`
Affected pull requests: `[fill in]`
First Changed Commit(s): `[fill in]`
Orphaned LFS objects: `[none, or attach the file named by git-filter-repo]`

Please permanently remove the cached views and references associated with the rewritten history, and run the required server-side garbage collection for the sensitive data. No credentials or private repository data are included in this request.

Thank you.
