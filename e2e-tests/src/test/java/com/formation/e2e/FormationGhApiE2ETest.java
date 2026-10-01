package com.formation.e2e;

import io.github.bonigarcia.wdm.WebDriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.openqa.selenium.By;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.logging.LogType;
import org.openqa.selenium.logging.LoggingPreferences;
import org.openqa.selenium.support.ui.ExpectedCondition;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.LocalDate;
import java.time.DayOfWeek;
import java.time.format.DateTimeFormatter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
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
    private static final Path REPORT_CSV = Paths.get("target", "reporting", "e2e-test-steps.csv");

    /**
     * Erreur connue et ignorée volontairement : le fichier CSS genere par Blazor
     * (FormationGhApi.Web.styles.css) n'est pas present sur le deploiement GitHub Pages
     * et renvoie une 404. Cela n'empeche pas l'application de fonctionner.
     */
    private static final String IGNORED_CSS_404 = "FormationGhApi.Web.styles.css";
    private static final DateTimeFormatter ISO_DATE = DateTimeFormatter.ISO_LOCAL_DATE;

    private WebDriver driver;
    private WebDriverWait wait;
    private Path screenshotDirectory;
    private int screenshotIndex;
    private String testMethodName;
    private String testDisplayName;
    private final List<StepResult> stepResults = new ArrayList<>();

    @BeforeAll
    static void initialiserRapport() throws IOException {
        Files.createDirectories(REPORT_CSV.getParent());
        Files.writeString(REPORT_CSV,
                "test_method;test_case;step;status;detail;duration_ms" + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }

    /**
     * Prépare le navigateur Chrome en mode headless avec la journalisation des erreurs.
     */
    @BeforeEach
    void setUp(TestInfo testInfo) {
        testMethodName = testInfo.getTestMethod()
                .map(method -> method.getName())
                .orElse(testInfo.getDisplayName());
        testDisplayName = testInfo.getDisplayName();
        screenshotDirectory = Paths.get("target", "screenshots", nettoyerNom(testMethodName));
        try {
            Files.createDirectories(screenshotDirectory);
        } catch (Exception e) {
            throw new IllegalStateException("Impossible de créer le dossier de captures d'écran", e);
        }
        screenshotIndex = 0;

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
        try {
            if (driver != null) {
                driver.quit();
            }
        } finally {
            ecrireRapportEtapes();
        }
    }

    /**
     * Vérifie que la page d'accueil affiche la liste attendue des utilisateurs.
     */
    @Test
    @DisplayName("La page d'accueil affiche les utilisateurs")
    void laPageDAccueilAfficheLesUtilisateurs() {
        executerEtape("Charger la page d'accueil", () -> {
            ouvrirPage(APP_URL, driver1 -> !driver1.findElements(By.cssSelector("a.user-card")).isEmpty());
            return "URL chargée";
        });
        executerEtape("Attendre le rendu de la page d'accueil", () -> {
            attendreChargementAccueil();
            return "Le body et les cartes utilisateurs sont visibles";
        });
        executerEtape("Capturer la page d'accueil", () -> "Capture enregistrée : " + capturerCaptureEcran("page-accueil"));
        executerEtape("Vérifier la liste des utilisateurs", () -> {
            List<WebElement> cartesUtilisateurs = driver.findElements(By.cssSelector("a.user-card"));
            assertEquals(3, cartesUtilisateurs.size(), "La page d'accueil doit lister 3 utilisateurs");
            assertTrue(cartesUtilisateurs.get(0).getText().contains("Jean Dupont"));
            assertTrue(cartesUtilisateurs.get(0).getText().contains("jean.dupont@formation.local"));
            assertTrue(cartesUtilisateurs.get(1).getText().contains("Sophie Martin"));
            assertTrue(cartesUtilisateurs.get(2).getText().contains("Luc Bernard"));
            return "3 utilisateurs trouvés";
        });
        executerEtape("Vérifier la console navigateur", () -> {
            verifierConsoleSansErreur();
            return "Aucune erreur console bloquante";
        });
    }

    /**
     * Vérifie le parcours complet de consultation, création, rechargement et suppression d'un congé.
     */
    @Test
    @DisplayName("Un utilisateur peut poser, recharger puis supprimer un congé")
    void unUtilisateurPeutPoserConsulterPuisSupprimerUnConge() {
        executerEtape("Ouvrir la fiche utilisateur", () -> {
            ouvrirUtilisateur(1);
            return "Utilisateur 1 chargé";
        });
        executerEtape("Capturer la fiche utilisateur", () -> "Capture enregistrée : " + capturerCaptureEcran("detail-utilisateur"));
        executerEtape("Vérifier l'entête et les soldes initiaux", () -> {
            assertTrue(driver.getTitle().contains("Jean Dupont"));
            assertTrue(driver.findElement(By.cssSelector("h1")).getText().contains("Jean Dupont"));
            assertTrue(driver.findElement(By.cssSelector(".back-link")).getText().contains("Tous les utilisateurs"));
            assertBalance("25", "25", "0");
            return "Soldes initiaux vérifiés";
        });
        executerEtape("Saisir une période de congé valide", () -> {
            saisirPeriode(periodeValide());
            return "Période de 3 jours ouvrés saisie";
        });
        executerEtape("Capturer la période saisie", () -> "Capture enregistrée : " + capturerCaptureEcran("periode-saisie"));
        executerEtape("Valider le congé et vérifier l'ajout", () -> {
            assertTrue(boutonPoserConge().isEnabled());
            boutonPoserConge().click();
            attendreNombreConges(1);
            assertBalance("22", "25", "3");
            assertTrue(driver.findElement(By.cssSelector(".leave-row")).getText().contains("3 jour(s) ouvré(s)"));
            return "Conge posé et soldes mis à jour";
        });
        executerEtape("Capturer le congé posé", () -> "Capture enregistrée : " + capturerCaptureEcran("conge-pose"));
        executerEtape("Recharger la page et vérifier la persistance", () -> {
            driver.navigate().refresh();
            authentifierSiNecessaire(driver1 -> !driver1.findElements(By.cssSelector(".balance-grid")).isEmpty());
            attendreChargementUtilisateur();
            assertEquals(1, nombreConges());
            return "Congé conservé après rechargement";
        });
        executerEtape("Capturer l'état après rechargement", () -> "Capture enregistrée : " + capturerCaptureEcran("apres-rechargement"));
        executerEtape("Supprimer le congé et vérifier le retour à l'état initial", () -> {
            supprimerPremierConge();
            attendreNombreConges(0);
            assertBalance("25", "25", "0");
            return "Congé supprimé";
        });
        executerEtape("Capturer l'état final", () -> "Capture enregistrée : " + capturerCaptureEcran("conge-supprime"));
        executerEtape("Vérifier la console navigateur", () -> {
            verifierConsoleSansErreur();
            return "Aucune erreur console bloquante";
        });
    }

    /**
     * Vérifie qu'une période sans jour ouvré ne peut pas être validée.
     */
    @Test
    @DisplayName("Une période sans jour ouvré est refusée")
    void unePeriodeSansJourOuvreEstRefusee() {
        executerEtape("Ouvrir la fiche utilisateur", () -> {
            ouvrirUtilisateur(1);
            return "Utilisateur 1 chargé";
        });
        executerEtape("Capturer la fiche utilisateur", () -> "Capture enregistrée : " + capturerCaptureEcran("detail-utilisateur"));
        executerEtape("Saisir une période sans jour ouvré", () -> {
            LocalDate samedi = prochainJour(DayOfWeek.SATURDAY);
            saisirPeriode(new PeriodeConge(samedi, samedi.plusDays(1)));
            return "Période couvrant uniquement le week-end saisie";
        });
        executerEtape("Capturer la période refusée", () -> "Capture enregistrée : " + capturerCaptureEcran("periode-sans-jour-ouvree"));
        executerEtape("Vérifier le refus de validation", () -> {
            assertFalse(boutonPoserConge().isEnabled());
            assertTrue(driver.findElement(By.cssSelector(".form-hint")).getText()
                    .contains("Choisissez une période contenant au moins un jour ouvré."));
            return "Bouton de validation désactivé";
        });
        executerEtape("Vérifier la console navigateur", () -> {
            verifierConsoleSansErreur();
            return "Aucune erreur console bloquante";
        });
    }

    /**
     * Vérifie qu'un congé en chevauchement affiche bien une erreur métier.
     */
    @Test
    @DisplayName("Une période qui chevauche un congé affiche une erreur")
    void unePeriodeQuiChevaucheUnCongeAfficheUneErreur() {
        executerEtape("Ouvrir la fiche utilisateur", () -> {
            ouvrirUtilisateur(1);
            return "Utilisateur 1 chargé";
        });
        executerEtape("Capturer la fiche utilisateur", () -> "Capture enregistrée : " + capturerCaptureEcran("detail-utilisateur"));
        executerEtape("Poser un premier congé", () -> {
            PeriodeConge periode = periodeValide();
            saisirPeriode(periode);
            boutonPoserConge().click();
            attendreNombreConges(1);
            return "Premier congé posé";
        });
        executerEtape("Capturer le premier congé", () -> "Capture enregistrée : " + capturerCaptureEcran("premier-conge-pose"));
        executerEtape("Tenter un congé chevauchant", () -> {
            PeriodeConge periode = periodeValide();
            saisirPeriode(periode);
            boutonPoserConge().click();
            wait.until(ExpectedConditions.textToBePresentInElementLocated(
                    By.cssSelector(".error-message"),
                    "chevauche un congé déjà posé"));
            return "Message d'erreur affiché";
        });
        executerEtape("Capturer l'erreur de chevauchement", () -> "Capture enregistrée : " + capturerCaptureEcran("erreur-chevauchement"));
        executerEtape("Vérifier que le congé existant est conservé", () -> {
            assertEquals(1, nombreConges());
            return "Un seul congé reste affiché";
        });
        executerEtape("Vérifier la console navigateur", () -> {
            verifierConsoleSansErreur();
            return "Aucune erreur console bloquante";
        });
    }

    /**
     * Vérifie qu'une période trop longue désactive le bouton de validation.
     */
    @Test
    @DisplayName("Une période trop longue désactive le bouton")
    void unePeriodeTropLongueDesactiveLeBouton() {
        executerEtape("Ouvrir la fiche utilisateur", () -> {
            ouvrirUtilisateur(1);
            return "Utilisateur 1 chargé";
        });
        executerEtape("Capturer la fiche utilisateur", () -> "Capture enregistrée : " + capturerCaptureEcran("detail-utilisateur"));
        executerEtape("Saisir une période trop longue", () -> {
            saisirPeriode(periodeTropLongue());
            return "Période de 41 jours saisie";
        });
        executerEtape("Capturer la période trop longue", () -> "Capture enregistrée : " + capturerCaptureEcran("periode-trop-longue"));
        executerEtape("Vérifier la désactivation du bouton", () -> {
            assertFalse(boutonPoserConge().isEnabled());
            assertTrue(driver.findElement(By.cssSelector(".form-hint")).getText()
                    .contains("jour(s) ouvré(s) sélectionné(s)"));
            return "Bouton de validation désactivé";
        });
        executerEtape("Vérifier la console navigateur", () -> {
            verifierConsoleSansErreur();
            return "Aucune erreur console bloquante";
        });
    }

    /**
     * Vérifie qu'une route inconnue affiche la page introuvable.
     */
    @Test
    @DisplayName("Les routes inconnues affichent la page introuvable")
    void lesRoutesInconnuesAffichentLaPageIntrouvable() {
        executerEtape("Ouvrir une route inconnue", () -> {
            ouvrirPage(APP_URL + "route-inconnue", driver1 -> driver1.findElements(By.tagName("h1")).stream()
                    .anyMatch(heading -> heading.getText().contains("Page introuvable")));
            return "Route inconnue chargée";
        });
        executerEtape("Attendre la page introuvable", () -> {
            wait.until(ExpectedConditions.textToBePresentInElementLocated(By.tagName("h1"), "Page introuvable"));
            return "Message d'erreur de navigation affiché";
        });
        executerEtape("Capturer la page introuvable", () -> "Capture enregistrée : " + capturerCaptureEcran("page-introuvable"));
        executerEtape("Vérifier le contenu de la page introuvable", () -> {
            assertTrue(driver.findElement(By.tagName("body")).getText().contains("La page demandée n’existe pas."));
            return "Page introuvable conforme";
        });
        executerEtape("Vérifier la console navigateur", () -> {
            verifierConsoleSansErreur();
            return "Aucune erreur console bloquante";
        });
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
        ouvrirPage(APP_URL + "user/" + id,
                driver1 -> !driver1.findElements(By.cssSelector(".balance-grid")).isEmpty());
        attendreChargementUtilisateur();
    }

    private void ouvrirPage(String url, ExpectedCondition<Boolean> pageChargee) {
        driver.get(url);
        authentifierSiNecessaire(pageChargee);
    }

    private void authentifierSiNecessaire(ExpectedCondition<Boolean> pageChargee) {
        wait.until(driver1 -> !driver1.findElements(By.cssSelector("input[type='password']")).isEmpty()
                || pageChargee.apply(driver1));

        List<WebElement> champsMotDePasse = driver.findElements(By.cssSelector("input[type='password']"));
        if (champsMotDePasse.isEmpty()) {
            return;
        }

        String motDePasse = System.getenv("E2E_APP_PASSWORD");
        if (motDePasse == null || motDePasse.isBlank()) {
            throw new IllegalStateException("La variable d'environnement E2E_APP_PASSWORD est requise.");
        }

        champsMotDePasse.get(0).sendKeys(motDePasse);
        driver.findElement(By.cssSelector(".auth-card button[type='submit']")).click();
        wait.until(pageChargee);
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
     * Exécute une étape de test, en capture le résultat et sa durée.
     */
    private void executerEtape(String etape, ThrowingSupplier<String> action) {
        long debut = System.nanoTime();
        try {
            String detail = action.get();
            stepResults.add(new StepResult(etape, "SUCCES", detail == null ? "" : detail, dureeMs(debut)));
        } catch (Throwable throwable) {
            stepResults.add(new StepResult(etape, "ECHEC", messageErreur(throwable), dureeMs(debut)));
            rethrowUnchecked(throwable);
        }
    }

    /**
     * Retourne la durée d'exécution d'une étape en millisecondes.
     */
    private long dureeMs(long debutNano) {
        return Math.max(0L, (System.nanoTime() - debutNano) / 1_000_000L);
    }

    /**
     * Renvoie un message d'erreur exploitable dans le fichier de suivi.
     */
    private String messageErreur(Throwable throwable) {
        if (throwable.getMessage() != null && !throwable.getMessage().isBlank()) {
            return throwable.getMessage();
        }
        return throwable.getClass().getSimpleName();
    }

    /**
     * Réécrit proprement une exception non vérifiée.
     */
    @SuppressWarnings("unchecked")
    private static <T extends Throwable> void rethrowUnchecked(Throwable throwable) throws T {
        throw (T) throwable;
    }

    /**
     * Ecrit les résultats du scénario courant dans un fichier CSV.
     */
    private void ecrireRapportEtapes() {
        if (stepResults.isEmpty()) {
            return;
        }

        List<String> lignes = new ArrayList<>();
        for (StepResult stepResult : stepResults) {
            lignes.add(String.join(";",
                    csvEscape(testMethodName),
                    csvEscape(testDisplayName),
                    csvEscape(stepResult.step()),
                    csvEscape(stepResult.status()),
                    csvEscape(stepResult.detail()),
                    Long.toString(stepResult.durationMs())));
        }

        try {
            Files.writeString(REPORT_CSV,
                    String.join(System.lineSeparator(), lignes) + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new IllegalStateException("Impossible d'écrire le rapport de test CSV", e);
        } finally {
            stepResults.clear();
        }
    }

    /**
     * Echappe une valeur au format CSV.
     */
    private String csvEscape(String valeur) {
        if (valeur == null) {
            return "";
        }

        String echappee = valeur.replace("\"", "\"\"");
        if (echappee.contains(";") || echappee.contains("\"") || echappee.contains("\n") || echappee.contains("\r")) {
            return "\"" + echappee + "\"";
        }
        return echappee;
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

    /**
     * Capture une image de l'état courant du test.
     */
    private String capturerCaptureEcran(String etape) {
        if (!(driver instanceof TakesScreenshot takesScreenshot)) {
            return "";
        }

        screenshotIndex++;
        String nomFichier = String.format("%02d-%s.png", screenshotIndex, nettoyerNom(etape));
        Path destination = screenshotDirectory.resolve(nomFichier);
        try {
            Files.copy(takesScreenshot.getScreenshotAs(OutputType.FILE).toPath(), destination, StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception e) {
            throw new IllegalStateException("Impossible de capturer la capture d'écran " + nomFichier, e);
        }
        return destination.toString();
    }

    /**
     * Nettoie un nom pour l'utiliser dans un chemin de fichier.
     */
    private String nettoyerNom(String valeur) {
        return valeur.toLowerCase()
                .replaceAll("[^a-z0-9]+", "-")
                .replaceAll("^-+|-+$", "");
    }

    /**
     * Représente une étape de test.
     */
    private record StepResult(String step, String status, String detail, long durationMs) {
    }

    private record PeriodeConge(LocalDate debut, LocalDate fin) {
    }

    @FunctionalInterface
    private interface ThrowingSupplier<T> {
        T get() throws Exception;
    }
}
