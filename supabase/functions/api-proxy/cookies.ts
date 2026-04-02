export function rewriteProxySetCookie(setCookie: string): string {
  let rewritten = setCookie;
  if (/;\s*SameSite=/i.test(rewritten)) {
    rewritten = rewritten.replace(/;\s*SameSite=[^;]*/i, '; SameSite=None');
  } else {
    rewritten = `${rewritten}; SameSite=None`;
  }
  if (!/;\s*Secure\b/i.test(rewritten)) {
    rewritten = `${rewritten}; Secure`;
  }
  return rewritten;
}
