package com.formation.e2e;

import io.github.bonigarcia.wdm.WebDriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.openqa.selenium.By;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.logging.LogType;
import org.openqa.selenium.logging.LoggingPreferences;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import java.time.Duration;
import java.time.LocalDate;
import java.time.DayOfWeek;
import java.time.format.DateTimeFormatter;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Test end to end de l'application https://aouzgaga.github.io/formation-gh-api/
 *
 * Parcours couverts :
 * - chargement de la page d'accueil et affichage des utilisateurs
 * - consultation d'un utilisateur
 * - creation, persistence et suppression d'un conge
 * - validation des cas d'erreur metier
 * - page introuvable pour les routes inconnues
 */
class FormationGhApiE2ETest {

    private static final String APP_URL = "https://aouzgaga.github.io/formation-gh-api/";

    /**
     * Erreur connue et ignorée volontairement : le fichier CSS genere par Blazor
     * (FormationGhApi.Web.styles.css) n'est pas present sur le deploiement GitHub Pages
     * et renvoie une 404. Cela n'empeche pas l'application de fonctionner.
     */
    private static final String IGNORED_CSS_404 = "FormationGhApi.Web.styles.css";
    private static final DateTimeFormatter ISO_DATE = DateTimeFormatter.ISO_LOCAL_DATE;

    private WebDriver driver;
    private WebDriverWait wait;

    /**
     * Prépare le navigateur Chrome en mode headless avec la journalisation des erreurs.
     */
    @BeforeEach
    void setUp() {
        setupChromeDriver();

        ChromeOptions options = new ChromeOptions();
        options.addArguments("--headless=new");
        options.addArguments("--no-sandbox");
        options.addArguments("--disable-dev-shm-usage");
        options.addArguments("--disable-gpu");
        options.addArguments("--window-size=1920,1080");
        options.addArguments("--ignore-certificate-errors");
        options.setAcceptInsecureCerts(true);

        LoggingPreferences loggingPreferences = new LoggingPreferences();
        loggingPreferences.enable(LogType.BROWSER, java.util.logging.Level.SEVERE);
        options.setCapability("goog:loggingPrefs", loggingPreferences);

        driver = new ChromeDriver(options);
        wait = new WebDriverWait(driver, Duration.ofSeconds(30));
    }

    /**
     * Configure le driver Chrome a utiliser. Si un chromedriver est deja installe sur la
     * machine (variable d'environnement WEBDRIVER_CHROME_DRIVER ou chemins systeme usuels),
     * il est reutilise directement ; sinon, WebDriverManager telecharge automatiquement la
     * version adaptee a la version de Chrome installee.
     */
    private static void setupChromeDriver() {
        String existingDriverPath = System.getenv("WEBDRIVER_CHROME_DRIVER");
        if (existingDriverPath == null || existingDriverPath.isBlank()) {
            for (String candidate : new String[] {"/usr/bin/chromedriver", "/usr/local/bin/chromedriver"}) {
                if (new java.io.File(candidate).exists()) {
                    existingDriverPath = candidate;
                    break;
                }
            }
        }

        if (existingDriverPath != null && !existingDriverPath.isBlank()) {
            System.setProperty("webdriver.chrome.driver", existingDriverPath);
        } else {
            WebDriverManager.chromedriver().setup();
        }
    }

    /**
     * Ferme proprement le navigateur après chaque scénario.
     */
    @AfterEach
    void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }

    /**
     * Vérifie que la page d'accueil affiche la liste attendue des utilisateurs.
     */
    @Test
    void laPageDAccueilAfficheLesUtilisateurs() {
        driver.get(APP_URL);
        attendreChargementAccueil();

        List<WebElement> cartesUtilisateurs = driver.findElements(By.cssSelector("a.user-card"));
        assertEquals(3, cartesUtilisateurs.size(), "La page d'accueil doit lister 3 utilisateurs");
        assertTrue(cartesUtilisateurs.get(0).getText().contains("Jean Dupont"));
        assertTrue(cartesUtilisateurs.get(0).getText().contains("jean.dupont@formation.local"));
        assertTrue(cartesUtilisateurs.get(1).getText().contains("Sophie Martin"));
        assertTrue(cartesUtilisateurs.get(2).getText().contains("Luc Bernard"));

        verifierConsoleSansErreur();
    }

    /**
     * Vérifie le parcours complet de consultation, création, rechargement et suppression d'un congé.
     */
    @Test
    void unUtilisateurPeutPoserConsulterPuisSupprimerUnConge() {
        ouvrirUtilisateur(1);

        assertTrue(driver.getTitle().contains("Jean Dupont"));
        assertTrue(driver.findElement(By.cssSelector("h1")).getText().contains("Jean Dupont"));
        assertTrue(driver.findElement(By.cssSelector(".back-link")).getText().contains("Tous les utilisateurs"));
        assertBalance("25", "25", "0");

        PeriodeConge periode = periodeValide();
        saisirPeriode(periode);
        assertTrue(boutonPoserConge().isEnabled());
        boutonPoserConge().click();

        attendreNombreConges(1);
        assertBalance("22", "25", "3");
        assertTrue(driver.findElement(By.cssSelector(".leave-row")).getText().contains("3 jour(s) ouvré(s)"));

        driver.navigate().refresh();
        attendreChargementUtilisateur();
        assertEquals(1, nombreConges());

        supprimerPremierConge();
        attendreNombreConges(0);
        assertBalance("25", "25", "0");

        verifierConsoleSansErreur();
    }

    /**
     * Vérifie qu'une période sans jour ouvré ne peut pas être validée.
     */
    @Test
    void unePeriodeSansJourOuvreEstRefusee() {
        ouvrirUtilisateur(1);

        LocalDate samedi = prochainJour(DayOfWeek.SATURDAY);
        saisirPeriode(new PeriodeConge(samedi, samedi.plusDays(1)));

        assertFalse(boutonPoserConge().isEnabled());
        assertTrue(driver.findElement(By.cssSelector(".form-hint")).getText()
                .contains("Choisissez une période contenant au moins un jour ouvré."));

        verifierConsoleSansErreur();
    }

    /**
     * Vérifie qu'un congé en chevauchement affiche bien une erreur métier.
     */
    @Test
    void unePeriodeQuiChevaucheUnCongeAfficheUneErreur() {
        ouvrirUtilisateur(1);

        PeriodeConge periode = periodeValide();
        saisirPeriode(periode);
        boutonPoserConge().click();
        attendreNombreConges(1);

        saisirPeriode(periode);
        boutonPoserConge().click();

        wait.until(ExpectedConditions.textToBePresentInElementLocated(
                By.cssSelector(".error-message"),
                "chevauche un congé déjà posé"));
        assertEquals(1, nombreConges());

        verifierConsoleSansErreur();
    }

    /**
     * Vérifie qu'une période trop longue désactive le bouton de validation.
     */
    @Test
    void unePeriodeTropLongueDesactiveLeBouton() {
        ouvrirUtilisateur(1);

        PeriodeConge periode = periodeTropLongue();
        saisirPeriode(periode);

        assertFalse(boutonPoserConge().isEnabled());
        assertTrue(driver.findElement(By.cssSelector(".form-hint")).getText()
                .contains("jour(s) ouvré(s) sélectionné(s)"));

        verifierConsoleSansErreur();
    }

    /**
     * Vérifie qu'une route inconnue affiche la page introuvable.
     */
    @Test
    void lesRoutesInconnuesAffichentLaPageIntrouvable() {
        driver.get(APP_URL + "route-inconnue");

        wait.until(ExpectedConditions.textToBePresentInElementLocated(By.tagName("h1"), "Page introuvable"));
        assertTrue(driver.findElement(By.tagName("body")).getText().contains("La page demandée n’existe pas."));

        verifierConsoleSansErreur();
    }

    /**
     * Attend que la page d'accueil soit entièrement rendue et que la liste des utilisateurs apparaisse.
     */
    private void attendreChargementAccueil() {
        wait.until(ExpectedConditions.presenceOfElementLocated(By.tagName("body")));
        wait.until(driver1 ->
                ((JavascriptExecutor) driver1).executeScript("return document.readyState").equals("complete"));
        wait.until(ExpectedConditions.numberOfElementsToBeMoreThan(By.cssSelector("a.user-card"), 0));
    }

    /**
     * Attend que l'écran détail utilisateur soit chargé avec les cartes de solde visibles.
     */
    private void attendreChargementUtilisateur() {
        wait.until(ExpectedConditions.presenceOfElementLocated(By.tagName("body")));
        wait.until(driver1 ->
                ((JavascriptExecutor) driver1).executeScript("return document.readyState").equals("complete"));
        wait.until(driver1 -> !driver1.findElements(By.cssSelector(".balance-grid")).isEmpty());
    }

    /**
     * Ouvre la page de détail d'un utilisateur par identifiant.
     */
    private void ouvrirUtilisateur(int id) {
        driver.get(APP_URL + "user/" + id);
        attendreChargementUtilisateur();
    }

    /**
     * Vérifie qu'aucune erreur console bloquante n'a été enregistrée.
     */
    private void verifierConsoleSansErreur() {
        List<org.openqa.selenium.logging.LogEntry> consoleLogs = driver.manage().logs()
                .get(LogType.BROWSER)
                .getAll()
                .stream()
                .filter(entry -> entry.getLevel().equals(java.util.logging.Level.SEVERE))
                .filter(entry -> !entry.getMessage().contains("Failed to load resource: the server responded with a status of 404"))
                .toList();
        assertTrue(consoleLogs.isEmpty(),
                "Des erreurs ont ete detectees dans la console du navigateur : " + consoleLogs);
    }

    /**
     * Vérifie les trois indicateurs de solde affichés dans la vue utilisateur.
     */
    private void assertBalance(String solde, String acquis, String pris) {
        List<WebElement> cartes = driver.findElements(By.cssSelector(".balance-card strong"));
        assertEquals(3, cartes.size(), "La page utilisateur doit afficher 3 cartes de solde");
        assertTrue(cartes.get(0).getText().startsWith(solde));
        assertTrue(cartes.get(1).getText().startsWith(acquis));
        assertTrue(cartes.get(2).getText().startsWith(pris));
    }

    /**
     * Construit une période valide de trois jours ouvrés pour les tests.
     */
    private PeriodeConge periodeValide() {
        LocalDate debut = prochainJour(DayOfWeek.MONDAY);
        return new PeriodeConge(debut, debut.plusDays(2));
    }

    /**
     * Construit une période volontairement trop longue pour déclencher la validation.
     */
    private PeriodeConge periodeTropLongue() {
        LocalDate debut = prochainJour(DayOfWeek.MONDAY);
        return new PeriodeConge(debut, debut.plusDays(40));
    }

    /**
     * Retourne la prochaine date correspondant au jour de semaine demandé.
     */
    private LocalDate prochainJour(DayOfWeek dayOfWeek) {
        LocalDate date = LocalDate.now().plusDays(1);
        while (date.getDayOfWeek() != dayOfWeek) {
            date = date.plusDays(1);
        }
        return date;
    }

    /**
     * Renseigne les deux champs date du formulaire de congé.
     */
    private void saisirPeriode(PeriodeConge periode) {
        List<WebElement> champsDate = driver.findElements(By.cssSelector("input[type='date']"));
        remplirChampDate(champsDate.get(0), periode.debut());
        remplirChampDate(champsDate.get(1), periode.fin());
    }

    /**
     * Injecte une date dans un champ HTML et déclenche les événements de saisie attendus.
     */
    private void remplirChampDate(WebElement input, LocalDate date) {
        String value = date.format(ISO_DATE);
        ((JavascriptExecutor) driver).executeScript("""
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, input, value);
    }

    /**
     * Retourne le bouton de validation du congé.
     */
    private WebElement boutonPoserConge() {
        return driver.findElement(By.cssSelector("button.primary-button"));
    }

    /**
     * Compte le nombre de congés affichés dans l'historique.
     */
    private int nombreConges() {
        return driver.findElements(By.cssSelector(".leave-row")).size();
    }

    /**
     * Attend que l'historique contienne exactement le nombre de congés attendu.
     */
    private void attendreNombreConges(int nombreAttendu) {
        wait.until(ExpectedConditions.numberOfElementsToBe(By.cssSelector(".leave-row"), nombreAttendu));
    }

    /**
     * Supprime le premier congé affiché dans la liste.
     */
    private void supprimerPremierConge() {
        driver.findElement(By.cssSelector(".delete-button")).click();
    }

    private record PeriodeConge(LocalDate debut, LocalDate fin) {
    }
}
