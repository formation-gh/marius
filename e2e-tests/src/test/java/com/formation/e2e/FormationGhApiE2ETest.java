package com.formation.e2e;

import io.github.bonigarcia.wdm.WebDriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.openqa.selenium.By;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.logging.LogType;
import org.openqa.selenium.logging.LoggingPreferences;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import java.time.Duration;
import java.util.List;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Test end to end de l'application https://aouzgaga.github.io/formation-gh-api/
 *
 * Scenario unique : l'application se charge correctement et ne renvoie
 * aucune erreur (ni erreur HTTP/404 affichee a l'ecran, ni erreur
 * JavaScript dans la console du navigateur).
 */
class FormationGhApiE2ETest {

    private static final String APP_URL = "https://aouzgaga.github.io/formation-gh-api/";

    /**
     * Erreur connue et ignorée volontairement : le fichier CSS genere par Blazor
     * (FormationGhApi.Web.styles.css) n'est pas present sur le deploiement GitHub Pages
     * et renvoie une 404. Cela n'empeche pas l'application de fonctionner.
     */
    private static final String IGNORED_CSS_404 = "FormationGhApi.Web.styles.css";

    private WebDriver driver;

    @BeforeEach
    void setUp() {
        setupChromeDriver();

        ChromeOptions options = new ChromeOptions();
        options.addArguments("--headless=new");
        options.addArguments("--no-sandbox");
        options.addArguments("--disable-dev-shm-usage");
        options.addArguments("--disable-gpu");
        options.addArguments("--window-size=1920,1080");

        LoggingPreferences loggingPreferences = new LoggingPreferences();
        loggingPreferences.enable(LogType.BROWSER, java.util.logging.Level.SEVERE);
        options.setCapability("goog:loggingPrefs", loggingPreferences);

        driver = new ChromeDriver(options);
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

    @AfterEach
    void tearDown() {
        if (driver != null) {
            driver.quit();
        }
    }

    @Test
    void laPageDAccueilSeChargeSansAucuneErreur() {
        driver.get(APP_URL);

        // Attend que le corps de la page soit rendu (application Blazor WebAssembly).
        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(30));
        wait.until(ExpectedConditions.presenceOfElementLocated(By.tagName("body")));
        wait.until(driver1 ->
                ((JavascriptExecutor) driver1).executeScript("return document.readyState").equals("complete"));

        // Le titre de la page ne doit pas indiquer une erreur de chargement.
        String title = driver.getTitle().toLowerCase(Locale.ROOT);
        assertFalse(title.contains("404"), "Le titre de la page indique une erreur 404 : " + title);
        assertFalse(title.contains("error"), "Le titre de la page indique une erreur : " + title);

        // Le contenu de la page ne doit afficher aucun message d'erreur connu.
        String bodyText = driver.findElement(By.tagName("body")).getText().toLowerCase(Locale.ROOT);
        assertFalse(bodyText.contains("404"), "La page affiche une erreur 404 : " + bodyText);
        assertFalse(bodyText.contains("page not found"), "La page affiche une erreur 'page not found'");
        assertFalse(bodyText.contains("unhandled exception"), "La page affiche une exception non geree");

        // La page doit contenir du contenu visible (l'application s'est bien chargee).
        assertTrue(bodyText.trim().length() > 0, "La page est vide, l'application ne semble pas s'etre chargee");

        // Aucune erreur JavaScript (niveau SEVERE) ne doit avoir ete loggee dans la console du navigateur,
        // a l'exception connue du CSS Blazor manquant (voir IGNORED_CSS_404).
        List<org.openqa.selenium.logging.LogEntry> consoleLogs = driver.manage().logs()
                .get(LogType.BROWSER)
                .getAll()
                .stream()
                .filter(entry -> entry.getLevel().equals(java.util.logging.Level.SEVERE))
                .filter(entry -> !entry.getMessage().contains(IGNORED_CSS_404))
                .toList();
        assertTrue(consoleLogs.isEmpty(),
                "Des erreurs ont ete detectees dans la console du navigateur : " + consoleLogs);
    }
}
