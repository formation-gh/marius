# Tests end to end — formation-gh-api

Ce module contient un test end to end (E2E) écrit en Java qui vérifie que
l'application déployée sur GitHub Pages à l'adresse
[https://aouzgaga.github.io/formation-gh-api/](https://aouzgaga.github.io/formation-gh-api/)
se charge correctement et ne renvoie aucune erreur.

## Scénario testé

`FormationGhApiE2ETest#laPageDAccueilSeChargeSansAucuneErreur` :

1. Ouvre la page d'accueil de l'application dans un navigateur Chrome headless.
2. Attend que la page (application Blazor WebAssembly) soit entièrement chargée.
3. Vérifie que le titre et le contenu de la page ne contiennent aucun message
   d'erreur connu (404, "page not found", exception non gérée, etc.).
4. Vérifie que du contenu a bien été rendu (l'application s'est chargée).
5. Vérifie qu'aucune erreur de niveau `SEVERE` n'a été loggée dans la console
   du navigateur (erreurs JavaScript, ressources introuvables, etc.).

## Technologies utilisées

- Java 17
- Maven
- [Selenium WebDriver](https://www.selenium.dev/) pour piloter le navigateur
- [WebDriverManager](https://github.com/bonigarcia/webdrivermanager) pour
  gérer automatiquement le driver Chrome (`chromedriver`)
- JUnit 5

## Prérequis

- Java 17+
- Maven 3.6+
- Google Chrome (ou Chromium) installé sur la machine

Si un `chromedriver` est déjà installé sur la machine (par exemple dans
`/usr/bin/chromedriver`), il est automatiquement réutilisé. Sinon,
WebDriverManager télécharge la version compatible avec le Chrome installé
(nécessite un accès réseau à `googlechromelabs.github.io`). Il est également
possible de forcer l'emplacement du driver via la variable d'environnement
`WEBDRIVER_CHROME_DRIVER`.

## Exécuter les tests

```bash
cd e2e-tests
mvn test
```
