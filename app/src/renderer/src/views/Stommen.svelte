<script lang="ts">
  // The connection to Stommen: sign in as a person, fetch the Projekt with their Roller and Kontakter, sign out.
  // The password is handed to the main process and forgotten here; the session never comes to this side.
  import type { StommenState, StommenSync } from '../../../shared/types'
  import Glyph from '../lib/Glyph.svelte'
  import Icon from '../lib/Icon.svelte'
  import Row from '../lib/Row.svelte'
  import { failure } from '../lib/format'

  // `bare`: in Inställningar, as a pane of settings (lib/Row.svelte); else a page of the first run.
  let { stommen, changed, refresh, bare = false }: { stommen: StommenState; changed: (s: StommenState) => void; refresh: () => Promise<void>; bare?: boolean } = $props()
  const mac = window.api.platform === 'darwin'
  const GOES = 'Till Stommen går inloggningen och de protokoll du själv skickar. Ljud och utskrifter stannar på den här datorn.'

  // svelte-ignore state_referenced_locally
  let server = $state(stommen.server)
  let email = $state('')
  let password = $state('')
  let busy = $state<'' | 'in' | 'fetch' | 'out'>('')
  let problem = $state('')
  let brought = $state<StommenSync | null>(null)

  const WHEN = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'long', timeStyle: 'short' })
  const many = (n: number, one: string, more: string): string => (n === 1 ? one : `${n} ${more}`)

  async function fetchAll(): Promise<void> {
    busy = 'fetch'
    problem = ''
    try {
      brought = await window.api.stommenSync()
      await refresh()
    } catch (e) {
      problem = failure(e)
    } finally {
      changed(await window.api.stommenState()) // a session Stommen no longer takes shows as signed out
      busy = ''
    }
  }

  async function signIn(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    busy = 'in'
    problem = ''
    brought = null
    try {
      changed(await window.api.stommenSignIn(server, email, password))
      password = ''
    } catch (x) {
      problem = failure(x)
      busy = ''
      return
    }
    await fetchAll()
  }

  async function signOut(): Promise<void> {
    busy = 'out'
    problem = ''
    brought = null
    try {
      changed(await window.api.stommenSignOut())
    } catch (e) {
      problem = failure(e)
    } finally {
      busy = ''
    }
  }
</script>

{#snippet brought_()}
  {#if busy === 'fetch'}
    <span role="status">Hämtar Projekt, Roller och Kontakter.</span>
  {:else if brought}
    <span role="status">
      {many(brought.projects, 'Ett Projekt', 'Projekt')} hämtade, med {many(brought.people, 'en Kontakt', 'Kontakter')}.
      {#if brought.vacant}{many(brought.vacant, 'En Roll är vakant', 'Roller är vakanta')}.{/if}
    </span>
  {/if}
{/snippet}

{#if bare}
  {#if problem}
    <div class="note bad wide" role="alert"><Icon name="alert" /><p>{problem}</p></div>
  {/if}
  {#if stommen.connected}
    {@const when = stommen.syncedAt ? `Hämtat senast ${WHEN.format(new Date(stommen.syncedAt))}.` : 'Inget är hämtat än.'}
    {#if mac}
      <span class="lbl">Konto:</span>
      <div class="val" style="gap: 2px">
        <h2 class="t">Inloggad som {stommen.user}</h2>
        <p class="d">{stommen.organization}, på {stommen.server}.</p>
        <p class="d">{when}</p>
      </div>
      <span class="lbl"></span>
      <div class="val">
        <div class="row" style="gap: 8px">
          <button class="btn primary" disabled={busy !== ''} onclick={fetchAll}>Hämta från Stommen</button>
          <button class="btn" disabled={busy !== ''} onclick={signOut}>Logga ut</button>
        </div>
        {#if busy === 'fetch' || brought}<p>{@render brought_()}</p>{/if}
      </div>
    {:else}
      <div class="srow">
        <span class="ic"><Glyph name="person" /></span>
        <div class="tx"><h2 class="t">Inloggad som {stommen.user}</h2><span class="d">{stommen.organization}, på {stommen.server}.</span></div>
        <div class="ctl"><button class="btn" disabled={busy !== ''} onclick={signOut}>Logga ut</button></div>
      </div>
      <div class="srow">
        <span class="ic"><Glyph name="refresh" /></span>
        <div class="tx"><span class="t">Projekt, Roller och Kontakter</span><span class="d">{when} {@render brought_()}</span></div>
        <div class="ctl"><button class="btn primary" disabled={busy !== ''} onclick={fetchAll}>Hämta från Stommen</button></div>
      </div>
    {/if}
    <Row label="" title="Det som skickas" icon="lock" desc={GOES} />
    {#if !stommen.kept}
      <p class="d wide tail">Den här datorn har ingen nyckelring som Byggmöte kan spara inloggningen i. Du loggar in igen nästa gång appen startar.</p>
    {/if}
    <p class="d wide tail">
      Det Stommen säger gäller. Ett Projekt som byter namn där byter namn här, och den som inte längre är Kontakt i ett Projekt
      lämnar det här. Möten och protokoll rörs inte.
    </p>
  {:else}
    <form onsubmit={signIn} aria-labelledby="signin">
      {#if mac}
        <span class="lbl"></span>
        <div class="val" style="gap: 4px">
          <h2 id="signin" class="t">Logga in i Stommen</h2>
          <p class="d">Dina Projekt, Roller och Kontakter hämtas hit och protokoll kan skickas dit. Saknar du konto kan du <a href="https://stommen.io" target="_blank" rel="noreferrer">skaffa ett på stommen.io</a>.</p>
        </div>
      {:else}
        <div class="srow">
          <span class="ic"><Glyph name="stommen" /></span>
          <div class="tx">
            <h2 id="signin" class="t">Logga in i Stommen</h2>
            <span class="d">Dina Projekt, Roller och Kontakter hämtas hit och protokoll kan skickas dit. Saknar du konto kan du <a href="https://stommen.io" target="_blank" rel="noreferrer">skaffa ett på stommen.io</a>.</span>
          </div>
        </div>
      {/if}
      <Row label="E-post" for="email" icon="mail">
        <input id="email" class="field" style="width: 240px" type="email" required autocomplete="username" bind:value={email} />
      </Row>
      <Row label="Lösenord" for="password" icon="lock" desc="Lösenordet skickas till Stommen och sparas inte i Byggmöte.">
        <input id="password" class="field" style="width: 240px" type="password" required autocomplete="current-password" bind:value={password} />
      </Row>
      {#if mac}
        <span class="lbl"></span>
        <div class="val">
          <button class="btn primary" type="submit" disabled={busy !== '' || !server.trim() || !email.trim() || !password}>{busy === 'in' ? 'Loggar in' : 'Logga in'}</button>
          <details>
            <summary class="d">Avancerat</summary>
            <label class="d" for="server" style="display: block; margin: 6px 0 3px">Adress till Stommen</label>
            <input id="server" class="field" style="width: 240px" type="text" required autocomplete="url" spellcheck="false" bind:value={server} />
          </details>
          <p class="d">{GOES}</p>
        </div>
      {:else}
        <details class="exp">
          <summary class="srow"><span class="ic"><Glyph name="general" /></span><span class="tx"><span class="t">Avancerat</span><span class="d">Vilket Stommen appen loggar in i</span></span><span class="ctl muted"><Glyph name="down" size={12} /></span></summary>
          <div class="sc-row" style="min-height: 48px"><label class="name" for="server">Adress till Stommen</label><input id="server" class="field" style="width: 240px" type="text" required autocomplete="url" spellcheck="false" bind:value={server} /></div>
        </details>
        <Row label="" title="Det som skickas" icon="lock" desc={GOES} />
        <div class="actions">
          <button class="btn primary" type="submit" disabled={busy !== '' || !server.trim() || !email.trim() || !password}>{busy === 'in' ? 'Loggar in' : 'Logga in'}</button>
        </div>
      {/if}
    </form>
  {/if}
{:else}
<div class="page">
  <div class="page-head">
    <div>
      <h1>Stommen</h1>
      <p class="muted">
        Har du ett konto i Stommen, logga in här så hämtas dina Projekt, Roller och Kontakter hit och protokoll kan skickas dit.
        Saknar du konto kan du <a href="https://stommen.io" target="_blank" rel="noreferrer">skaffa ett på stommen.io</a>, eller hoppa över det här steget.
      </p>
    </div>
  </div>

  <div class="stack narrow">
    <div class="note">
      <Icon name="lock" />
      <p>Till Stommen går inloggningen och de protokoll du själv skickar. Ljud och utskrifter stannar på den här datorn.</p>
    </div>

    {#if problem}
      <div class="note bad" role="alert"><Icon name="alert" /><p>{problem}</p></div>
    {/if}

    {#if stommen.connected}
      <section class="card" aria-labelledby="who">
        <h2 id="who">Inloggad som {stommen.user}</h2>
        <p class="muted">{stommen.organization}, på {stommen.server}.</p>
        <p class="muted">{stommen.syncedAt ? `Hämtat senast ${WHEN.format(new Date(stommen.syncedAt))}.` : 'Inget är hämtat än.'}</p>
        {#if busy === 'fetch'}
          <p role="status" style="margin-top: 12px">Hämtar Projekt, Roller och Kontakter.</p>
        {:else if brought}
          <p role="status" style="margin-top: 12px">
            {many(brought.projects, 'Ett Projekt', 'Projekt')} hämtade, med {many(brought.people, 'en Kontakt', 'Kontakter')}.
            {#if brought.vacant}{many(brought.vacant, 'En Roll är vakant', 'Roller är vakanta')}.{/if}
          </p>
        {/if}
        <div class="row" style="margin-top: 16px">
          <button class="btn primary" disabled={busy !== ''} onclick={fetchAll}><Icon name="refresh" /> Hämta från Stommen</button>
          <button class="btn" disabled={busy !== ''} onclick={signOut}>Logga ut</button>
        </div>
        {#if !stommen.kept}
          <p class="small muted" style="margin-top: 12px">
            Den här datorn har ingen nyckelring som Byggmöte kan spara inloggningen i. Du loggar in igen nästa gång appen startar.
          </p>
        {/if}
      </section>
      <p class="small muted">
        Det Stommen säger gäller. Ett Projekt som byter namn där byter namn här, och den som inte längre är Kontakt i ett Projekt
        lämnar det här. Möten och protokoll rörs inte.
      </p>
    {:else}
      <form class="card form" onsubmit={signIn} aria-labelledby="signin">
        <h2 id="signin">Logga in i Stommen</h2>
        <div>
          <label class="label" for="email">E-post</label>
          <input id="email" class="field" type="email" required autocomplete="username" bind:value={email} />
        </div>
        <div>
          <label class="label" for="password">Lösenord</label>
          <input id="password" class="field" type="password" required autocomplete="current-password" bind:value={password} />
        </div>
        <div class="row">
          <button class="btn primary" type="submit" disabled={busy !== '' || !server.trim() || !email.trim() || !password}>
            {busy === 'in' ? 'Loggar in' : 'Logga in'}
          </button>
        </div>
        <details>
          <summary class="small muted">Avancerat</summary>
          <div style="margin-top: 8px">
            <label class="label" for="server">Adress till Stommen</label>
            <input id="server" class="field" type="text" required autocomplete="url" spellcheck="false" bind:value={server} />
          </div>
        </details>
        <p class="small muted">Lösenordet skickas till Stommen och sparas inte i Byggmöte.</p>
      </form>
    {/if}
  </div>
</div>
{/if}

<style>
  .tail { margin-top: -6px; }
  .narrow { max-width: 560px; }
  .form { display: flex; flex-direction: column; gap: 14px; }
  .form .field { width: 100%; }
</style>
